/* Windows 绿色版入口：所有子进程归入同一个作业对象。 */
const {app, BrowserWindow, Menu, dialog, shell} = require('electron');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const bundle = __dirname;
const dataRoot = process.env.MEDIA_FACTORY_HOME || path.join(app.getPath('appData'), 'MediaFactory');
fs.mkdirSync(dataRoot, {recursive: true});
app.setPath('userData', path.join(dataRoot, 'browser'));
let backend, window, closing = false, ports;
const token = crypto.randomBytes(32).toString('hex');
const readyFile = path.join(dataRoot, `ready-${process.pid}.json`);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function openWindow(url, existing) {
  const view = existing || new BrowserWindow({width: 1280, height: 900, title: 'Media Factory',
    webPreferences: {nodeIntegration: false, contextIsolation: true, sandbox: true}});
  view.webContents.setWindowOpenHandler(({url: target}) => {
    const parsed = new URL(target);
    if (parsed.hostname === '127.0.0.1' && [String(ports.agent), String(ports.webui)].includes(parsed.port)) openWindow(target);
    else if (['https:', 'http:'].includes(parsed.protocol)) shell.openExternal(target);
    return {action: 'deny'};
  });
  view.webContents.on('will-navigate', (event, target) => {
    const parsed = new URL(target);
    if (parsed.hostname !== '127.0.0.1' || ![String(ports.agent), String(ports.webui)].includes(parsed.port)) event.preventDefault();
  });
  view.webContents.on('dom-ready', () => {
    const page = new URL(view.webContents.getURL());
    if (page.hostname === '127.0.0.1' && page.port === String(ports.webui)) {
      view.webContents.executeJavaScript(fs.readFileSync(path.join(bundle, 'branding.js'), 'utf8'));
    }
  });
  view.loadURL(url);
  return view;
}

async function start() {
  if (!app.requestSingleInstanceLock()) return app.quit();
  app.on('second-instance', () => { if (window) {window.show(); window.focus();} });
  window = new BrowserWindow({width: 1100, height: 800, title: 'Media Factory',
    webPreferences: {nodeIntegration: false, contextIsolation: true, sandbox: true}});
  window.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><body style="background:#111827;color:#eee;font:20px system-ui;padding:80px"><h1>Media Factory</h1><p>正在启动聊天服务，请稍候。</p></body></html>'));
  window.on('closed', () => app.quit());
  const python = path.join(bundle, 'python', 'python.exe');
  if (!fs.existsSync(python)) throw new Error('缺少内嵌 Python，请运行完整构建脚本。');
  backend = spawn(python, ['-m', 'desktop.supervisor', '--home', dataRoot, '--bundle', bundle,
    '--parent-pid', String(process.pid), '--ready-file', readyFile], {
    cwd: path.join(bundle, 'project'), windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
    env: {...process.env, MEDIA_FACTORY_SESSION_TOKEN: token, PYTHONUTF8: '1',
      PATH: path.join(bundle, 'bin') + path.delimiter + process.env.PATH}
  });
  // 日志由 Python 在脱敏后写入，原始子进程输出不落盘。
  backend.stderr.resume();
  backend.stdout.resume();
  backend.on('exit', () => { if (!closing) {
    if (!process.argv.includes('--verify-desktop')) dialog.showErrorBox('后端已退出', '请查看数据目录中的脱敏日志。');
    app.quit();
  } });
  for (let attempt = 0; attempt < 1200; attempt++) {
    if (fs.existsSync(readyFile)) {ports = JSON.parse(fs.readFileSync(readyFile, 'utf8')); break;}
    if (backend.exitCode !== null) throw new Error('后端启动失败，请查看日志。');
    await delay(500);
  }
  if (!ports) throw new Error('后端启动超时，请查看数据目录中的日志。');
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {label: 'Media Factory', submenu: [
      {label: '聊天', click: () => window.loadURL(`http://127.0.0.1:${ports.webui}`)},
      {label: '打开数据目录', click: () => shell.openPath(dataRoot)},
      {type: 'separator'}, {label: '退出', click: () => app.quit()}
    ]}, {label: '编辑', submenu: [{role: 'copy'}, {role: 'paste'}, {role: 'selectAll'}]},
    {label: '查看', submenu: [{role: 'reload'}, {role: 'toggleDevTools'}]}
  ]));
  window = openWindow(`http://127.0.0.1:${ports.webui}`, window);
  if (process.argv.includes('--verify-desktop')) {
    window.webContents.once('did-finish-load', async () => {
      try {
        fs.writeFileSync(path.join(dataRoot, 'desktop-stage.txt'), '页面已加载');
        window.show(); window.focus(); window.webContents.setBackgroundThrottling(false);
        await delay(8000);
        await window.webContents.executeJavaScript(`Array.from(document.querySelectorAll('button')).find(button => /开始使用|Start using|Okay, let/i.test(button.textContent))?.click()`);
        await delay(500);
        const text = await window.webContents.executeJavaScript('document.body.innerText');
        const webuiModels = await window.webContents.executeJavaScript(`fetch('/api/models', {headers: localStorage.getItem('token') ? {'Authorization': 'Bearer ' + localStorage.getItem('token')} : {}}).then(r => r.json())`);
        fs.writeFileSync(path.join(dataRoot, 'desktop-stage.txt'), '已读取页面与模型列表');
        const models = await fetch(`http://127.0.0.1:${ports.agent}/v1/models`, {headers: {'Authorization': `Bearer ${token}`}}).then(response => response.json());
        const verification = {
          title: window.webContents.getTitle(), url: window.webContents.getURL(),
          visibleText: text.slice(0, 1500), modelCount: models.data.length,
          webuiModelCount: webuiModels.data?.length || 0,
          modelName: models.data[0]?.name,
          homeTitle: await window.webContents.executeJavaScript(`document.querySelector('[class~="max-w-[58rem]"] [class~="text-2xl"][class~="line-clamp-1"] span.line-clamp-1')?.textContent`),
          backendPid: backend.pid, agentPort: ports.agent, webuiPort: ports.webui
        };
        if (process.env.MEDIA_FACTORY_VERIFY_REAL_MODEL === '1') {
          const relay = await window.webContents.executeJavaScript(`fetch('/api/chat/completions', {
            method: 'POST', headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('token')},
            body: JSON.stringify({model: ${JSON.stringify(models.data[0].id)}, stream: false, chat_id: 'local:media-factory-portable-check',
              messages: [{role: 'user', content: '只调用一次 finance_get_production_config，用一句中文概括素材方案。禁止生产、写库或发布。'}]})
          }).then(async response => ({status: response.status, body: await response.json()}))`);
          verification.relayStatus = relay.status;
          verification.relayReply = relay.body.choices?.[0]?.message?.content || JSON.stringify(relay.body);
        }
        const image = await Promise.race([window.webContents.capturePage(), delay(15000).then(() => {throw new Error('窗口截图超时');})]);
        fs.writeFileSync(path.join(dataRoot, 'desktop-window.png'), image.toPNG());
        const overview = await fetch(`http://127.0.0.1:${ports.agent}/api/overview`, {headers: {'Authorization': `Bearer ${token}`}}).then(response => response.json());
        verification.traceRunCount = overview.runs?.length || 0;
        verification.chatWindowCount = BrowserWindow.getAllWindows().length;
        fs.writeFileSync(path.join(dataRoot, 'desktop-verification.json'), JSON.stringify(verification, null, 2));
      } catch (error) {
        fs.writeFileSync(path.join(dataRoot, 'desktop-failure.json'), JSON.stringify({error: error.message}));
      } finally {app.quit();}
    });
  }
}

app.on('before-quit', event => {
  if (closing) return;
  closing = true;
  if (backend && backend.exitCode === null) {
    event.preventDefault();
    fetch(`http://127.0.0.1:${ports?.agent}/api/shutdown`, {method: 'POST', headers: {'Authorization': `Bearer ${token}`}})
      .catch(() => {}).finally(() => {
        const timer = setTimeout(() => {backend.kill(); app.exit();}, 6000);
        backend.once('exit', () => {clearTimeout(timer); app.exit();});
      });
  }
  try {fs.unlinkSync(readyFile);} catch (_) {}
});
app.whenReady().then(start).catch(error => {
  if (process.argv.includes('--verify-desktop')) fs.writeFileSync(path.join(dataRoot, 'desktop-failure.json'), JSON.stringify({error: error.message}));
  else dialog.showErrorBox('启动失败', error.message);
  app.quit();
});
