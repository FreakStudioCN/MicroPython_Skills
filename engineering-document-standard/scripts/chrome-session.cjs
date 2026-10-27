// 可选 CDP 客户端：只连接已运行的浏览器，不启动 Chrome、不自动重连。
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const util = require('node:util');
const os = require('node:os');
const args = process.argv.slice(2);
function option(name) {
  const index = args.indexOf(name);
  if (index < 0) return undefined;
  if (!args[index + 1] || args[index + 1].startsWith('--')) throw Error(name+' 缺少参数');
  return args[index + 1];
}
if (args.includes('--help')) {
  console.log('node chrome-session.cjs [--discover | --file DevToolsActivePort | --endpoint ws://已核实的浏览器端点]');
  process.exit(0);
}
const explicitFile = option('--file');
const explicitEndpoint = option('--endpoint');
const positional = args[0] && !args[0].startsWith('--') ? args[0] : undefined;
if ((explicitFile || positional) && explicitEndpoint) throw Error('文件与端点只能指定一种');
const accepted = new Set(['--discover', '--file', '--endpoint']);
for (let i = 0; i < args.length; i++) {
  if (i === 0 && positional) continue;
  if (!accepted.has(args[i])) throw Error('未知参数：'+args[i]);
  if (args[i] === '--file' || args[i] === '--endpoint') i++;
}
const userHome = process.env.USERPROFILE || os.homedir();
const roots = [];
if (process.env.CHROME_USER_DATA_DIR) roots.push(process.env.CHROME_USER_DATA_DIR);
if (process.platform === 'win32') {
  // 沙箱可能重定向 LOCALAPPDATA，同时检查真实用户目录。
  if (process.env.LOCALAPPDATA) roots.push(path.join(process.env.LOCALAPPDATA, 'Google/Chrome/User Data'));
  roots.push(path.join(userHome, 'AppData/Local/Google/Chrome/User Data'));
} else if (process.platform === 'darwin') {
  roots.push(path.join(os.homedir(), 'Library/Application Support/Google/Chrome'));
} else {
  roots.push(path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'google-chrome'));
}
const candidates = [...new Set(roots.map(root => path.resolve(root, 'DevToolsActivePort')))];
function readEndpoint(file) {
  const [port, endpoint] = fs.readFileSync(file, 'utf8').trim().split(/\r?\n/);
  if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535 ||
      !/^\/devtools\/browser\/[A-Za-z0-9-]+$/.test(endpoint || '')) {
    throw Error('DevToolsActivePort 内容无效：'+file);
  }
  return 'ws://127.0.0.1:'+port+endpoint;
}
const discovered = candidates.map(file => {
  try { return {file, exists:true, valid:true, endpoint:readEndpoint(file)}; }
  catch (error) { return {file, exists:fs.existsSync(file), valid:false, error:error.code || error.message}; }
});
if (args.includes('--discover')) {
  console.log(JSON.stringify(discovered.map(({endpoint, ...entry}) => entry), null, 2));
  process.exit(0);
}
let endpoint = explicitEndpoint;
let portFile = explicitFile || positional;
if (portFile) {
  portFile = path.resolve(portFile);
  endpoint = readEndpoint(portFile);
} else if (!endpoint) {
  const valid = discovered.filter(entry => entry.valid);
  if (valid.length !== 1) throw Error(valid.length ?
    '存在多个有效端点文件，请用 --file 明确选择：'+valid.map(entry => entry.file).join('；') :
    '未找到有效 DevToolsActivePort；用 --discover 检查，或用 --file / --endpoint 指定现场端点');
  ({file:portFile, endpoint} = valid[0]);
}
const endpointURL = new URL(endpoint);
if (!['ws:', 'wss:'].includes(endpointURL.protocol) || endpointURL.username || endpointURL.password) {
  throw Error('需要不含登录凭据的 ws:// 或 wss:// 浏览器端点');
}
if (typeof WebSocket !== 'function') throw Error('此 Node.js 没有全局 WebSocket，请使用支持该接口的运行时');
if (portFile) console.log('CHROME_PORT_FILE', portFile);
const ws = new WebSocket(endpointURL.href);
const pending = new Map();
let seq = 0, sid, selectedTarget;
function failPending(message) {
  for (const p of pending.values()) { clearTimeout(p.timer); p.reject(Error(message)); }
  pending.clear();
}
ws.addEventListener('message', event => {
  const m = JSON.parse(event.data);
  if (m.method === 'Target.detachedFromTarget' && m.params?.sessionId === sid) {
    sid=undefined;selectedTarget=undefined;
  }
  const p = pending.get(m.id);
  if (!p) return;
  clearTimeout(p.timer); pending.delete(m.id);
  if (m.error) p.reject(Object.assign(Error(JSON.stringify(m.error)), {protocolMessage:m.error.message}));
  else p.resolve(m.result);
});
ws.addEventListener('error', e => { console.error('CHROME_ERROR', e.message || e.type); failPending('Chrome WebSocket error'); close(); process.exitCode=1; });
ws.addEventListener('close', e => { console.log('CHROME_DISCONNECTED', e.code); failPending('Chrome disconnected'); input.close(); });
function cdp(method, params = {}, sessionId) {
  if (ws.readyState !== WebSocket.OPEN) return Promise.reject(Error('连接尚未就绪或已经关闭；请检查状态，不要自动重发写入'));
  return new Promise((resolve, reject) => {
    const id = ++seq;
    const timer = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: '+method+'；先读取页面确认结果，不要直接重试写入')); }, 30000);
    pending.set(id, {resolve,reject,timer});
    ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));
  });
}
async function tabs() {
  return (await cdp('Target.getTargets')).targetInfos.filter(t => t.type === 'page').map(t => ({targetId:t.targetId,title:t.title,url:t.url}));
}
async function attach(targetId) {
  const found = (await tabs()).find(t => t.targetId === targetId);
  if (!found) {
    if (selectedTarget?.targetId === targetId) { sid=undefined;selectedTarget=undefined; }
    throw Error('标签页已失效，请重新 tabs()');
  }
  if (sid && selectedTarget?.targetId === targetId) return found;
  if (sid) {
    const previousSession = sid;
    sid=undefined;selectedTarget=undefined;
    try {
      await cdp('Target.detachFromTarget',{sessionId:previousSession});
    } catch (error) {
      // 标签页可能在枚举后关闭；只容忍确定的旧会话失效，其他错误继续上报。
      if (!/^(Session with given id not found\.?|No session with given id\.?)$/.test(error.protocolMessage || '')) throw error;
    }
  }
  const result = await cdp('Target.attachToTarget',{targetId,flatten:true});
  sid=result.sessionId;selectedTarget=found;
  return found;
}
async function ev(expression) {
  if (!sid) throw Error('先 tabs()，核对标题和网址，再 attach(targetId)');
  const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},sid);
  if(r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
async function click(x,y,button='left') {
  if (!sid) throw Error('尚未 attach');
  await cdp('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button,clickCount:1},sid);
  await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button,clickCount:1},sid);
}
async function screenshot(file) {
  if (!sid) throw Error('尚未 attach');
  const r=await cdp('Page.captureScreenshot',{format:'png'},sid);
  fs.writeFileSync(file,Buffer.from(r.data,'base64'));return path.resolve(file);
}
function status() { return {connected:ws.readyState===WebSocket.OPEN,target:selectedTarget,pending:pending.size}; }
function close() { ws.close(); input.close(); }
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
// 每行一个表达式；长流程用 async IIFE 或读取本地 .cjs 文件。串行执行，避免写入交错。
let queue=Promise.resolve();
const input=readline.createInterface({input:process.stdin,terminal:false});
input.on('close',()=>{if(ws.readyState===WebSocket.OPEN || ws.readyState===WebSocket.CONNECTING) ws.close();});
process.once('SIGINT',close);
process.once('SIGTERM',close);
input.on('line', line => {
  if (!line.trim()) return;
  queue=queue.then(async()=>{
    try { const result=await eval(line); console.log(util.inspect(result,{depth:8,colors:false,maxArrayLength:null})); }
    catch(e) { console.error('COMMAND_ERROR',e.message); }
  });
});
ws.addEventListener('open', async()=>{
  console.log('CHROME_CONNECTED');
  try { console.log(JSON.stringify(await cdp('Browser.getVersion'))); }
  catch(e) { console.error(e.message); }
});
setTimeout(()=>{if(ws.readyState===WebSocket.CONNECTING) console.log('连接仍在等待：检查 Chrome 是否显示远程调试授权；保留本进程，不要循环重启');},10000).unref();
