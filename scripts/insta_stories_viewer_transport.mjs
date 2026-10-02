// Website-internal, account-independent transport. No browser cookies or CAPTCHA
// solving. The public page supplies the normal connection nonce; keep it in RAM.
// Node >= 22 supplies fetch and WebSocket; no package installation is required.
const account = process.argv[2];
const base = 'https://insta-stories-viewer.com';
const limit = 2_000_000;
let socket;
let finished = false;
const finish = (value) => {
  if (finished) return;
  finished = true;
  clearTimeout(deadline);
  try { socket?.close(); } catch {}
  process.stdout.write(JSON.stringify(value) + '\n', () => process.exit(0));
};
const deadline = setTimeout(() => finish({transport_error: 'timeout'}), 75000);

async function read(path) {
  const response = await fetch(base + path, {
    redirect: 'error', signal: AbortSignal.timeout(25000),
    headers: {'User-Agent': 'HarmonicaObserveDiagnostic/1.0'},
  });
  if ([401, 403, 429].includes(response.status)) throw new Error(`http_${response.status}`);
  if (!response.ok) throw new Error('http_error');
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    size += value.length;
    if (size > limit) { await reader.cancel(); throw new Error('size_limit'); }
    chunks.push(Buffer.from(value));
  }
  const text = Buffer.concat(chunks).toString('utf8');
  if (/cf-chl-|verify you are human|<title>Just a moment/i.test(text)) throw new Error('verification_required');
  return text;
}

try {
  if (!/^[A-Za-z0-9._]{1,30}$/.test(account || '')) throw new Error('invalid_account');
  const html = await read(`/${account}/`);
  const needsUpdate = html.match(/var USER_NEED_UPDATE\s*=\s*(true|false);/);
  const username = html.match(/var USER_NAME\s*=\s*'([^']+)';/);
  if (!needsUpdate || username?.[1]?.toLowerCase() !== account.toLowerCase()) throw new Error('page_schema_changed');
  const connection = JSON.parse(await read('/connect/'));
  if (typeof connection.token !== 'string' || !connection.token) throw new Error('connection_refused');
  socket = new WebSocket('wss://insta-stories-viewer.com/socket.io/?EIO=4&transport=websocket');
  let searched = false;
  socket.addEventListener('error', () => finish({transport_error: 'socket_failed'}));
  socket.addEventListener('close', () => finish({transport_error: 'socket_closed'}));
  socket.addEventListener('message', event => {
    const packet = String(event.data);
    if (Buffer.byteLength(packet) > limit) return finish({transport_error: 'size_limit'});
    if (packet === '2') { socket.send('3'); return; }
    if (packet.startsWith('0')) { socket.send('40'); return; }
    if (packet.startsWith('44')) return finish({transport_error: 'connection_refused'});
    if (packet.startsWith('40') && !searched) {
      searched = true;
      socket.send('42' + JSON.stringify([needsUpdate[1] === 'true' ? 'search' : 'fakeSearch', {
        username: account, date: Date.now(), token: connection.token, serverType: 'stories',
      }]));
    } else if (packet.startsWith('42')) {
      try {
        const [name, payload] = JSON.parse(packet.slice(2));
        if (name === 'searchResult' && (['stories', 'stories-posts'].includes(payload?.data?.serverType)
            || payload?.data?.code === 429)) finish(payload);
      } catch { finish({transport_error: 'invalid_response'}); }
    }
  });
} catch (error) {
  const allowed = new Set(['http_401', 'http_403', 'http_429', 'http_error', 'size_limit',
    'verification_required', 'invalid_account', 'page_schema_changed', 'connection_refused']);
  finish({transport_error: allowed.has(error.message) ? error.message : 'request_failed'});
}
