const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {EventEmitter} = require('node:events');
const {test} = require('node:test');

const script = path.resolve(__dirname, '../chrome-session.cjs');
const source = fs.readFileSync(script, 'utf8');

function client() {
  const targets = new Map(['a', 'b'].map(id => [id, {targetId:id, type:'page', title:id, url:'about:blank'}]));
  const calls = [];
  let socket, detachError;
  class Socket extends EventTarget {
    static OPEN = 1;
    static CONNECTING = 0;
    constructor() { super(); this.readyState=1; socket=this; }
    message(value) { this.dispatchEvent(new MessageEvent('message', {data:JSON.stringify(value)})); }
    send(text) {
      const request = JSON.parse(text);
      calls.push(request);
      queueMicrotask(() => {
        let result = {};
        if (request.method === 'Target.getTargets') result={targetInfos:[...targets.values()]};
        if (request.method === 'Target.attachToTarget') result={sessionId:'session-'+request.params.targetId};
        if (request.method === 'Target.detachFromTarget' && detachError) {
          this.message({id:request.id, error:{code:-32001, message:detachError}});
          return;
        }
        this.message({id:request.id, result});
      });
    }
    close() { this.readyState=3; }
  }
  const input = new EventEmitter();
  input.close = () => {};
  const context = vm.createContext({
    WebSocket:Socket, URL, Buffer,
    setTimeout, clearTimeout,
    console:{log() {}, error() {}},
    process:{argv:['node', script, '--endpoint', 'ws://127.0.0.1:9222/devtools/browser/test'],
             env:{}, platform:'win32', stdin:{}, once() {}},
    require(name) {
      if (name === 'node:readline') return {createInterface:() => input};
      if (name === 'node:fs') return {existsSync:() => false, readFileSync() { throw Error('fixture'); }};
      return require(name);
    }
  });
  vm.runInContext(source, context, {filename:script});
  return {
    context, calls, targets,
    notify(sessionId) { socket.message({method:'Target.detachedFromTarget', params:{sessionId}}); },
    failDetach(message) { detachError=message; }
  };
}

test('关闭当前标签页后，同一连接可直接附加另一个标签页', async () => {
  const c=client();
  await c.context.attach('a');
  c.targets.delete('a');
  c.notify('session-a');
  assert.equal(c.context.status().target, undefined);
  assert.equal(c.context.status().connected, true);
  assert.equal((await c.context.attach('b')).targetId, 'b');
  assert.equal(c.calls.filter(x => x.method === 'Target.detachFromTarget').length, 0);
});

test('不相关或迟到的旧会话通知不会清除新会话', async () => {
  const c=client();
  await c.context.attach('a');
  c.notify('unrelated-session');
  assert.equal(c.context.status().target.targetId, 'a');
  await c.context.attach('b');
  c.notify('session-a');
  assert.equal(c.context.status().target.targetId, 'b');
});

test('枚举后旧会话失效的两种协议错误均允许继续切换', async () => {
  for (const message of ['No session with given id', 'Session with given id not found.']) {
    const c=client();
    await c.context.attach('a');
    c.failDetach(message);
    assert.equal((await c.context.attach('b')).targetId, 'b');
  }
});

test('其他 detach 错误保持可见，不继续附加新标签页', async () => {
  const c=client();
  await c.context.attach('a');
  c.failDetach('Unexpected protocol failure');
  await assert.rejects(c.context.attach('b'), /Unexpected protocol failure/);
  assert.equal(c.calls.filter(x => x.method === 'Target.attachToTarget').length, 1);
});

test('缺少关闭通知时，重复附加已关闭目标也不能返回过期缓存', async () => {
  const c=client();
  await c.context.attach('a');
  c.targets.delete('a');
  await assert.rejects(c.context.attach('a'), /标签页已失效/);
  assert.equal(c.context.status().target, undefined);
  assert.equal((await c.context.attach('b')).targetId, 'b');
});
