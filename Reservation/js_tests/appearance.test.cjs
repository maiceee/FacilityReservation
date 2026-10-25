const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../static/Reservation/js/appearance.js'),'utf8');
function setup({stored=null,dark=false,blocked=false,print=false}={}){
 const handlers={},winHandlers={},changes=[];let preference=stored;
 const root={dataset:{},style:{},hasAttribute:()=>print};
 const system={matches:dark,addEventListener:(event,fn)=>handlers.system=fn};
 const storage={getItem:()=>{if(blocked)throw Error('blocked');return preference;},setItem:(k,v)=>{if(blocked)throw Error('blocked');preference=v;}};
 const window={addEventListener:(event,fn)=>winHandlers[event]=fn};
 vm.runInNewContext(code,{document:{documentElement:root,querySelectorAll:()=>[],dispatchEvent:e=>changes.push(e.detail),addEventListener:(event,fn)=>handlers[event]=fn},window,
  localStorage:storage,matchMedia:()=>system,WeakMap,CustomEvent:class {constructor(type,init){this.detail=init.detail;}}});
 return{root,system,handlers,winHandlers,changes,api:window.SpasyoAppearance,stored:()=>preference,external:value=>{preference=value;winHandlers.storage({key:'spasyo.appearance'});}};
}
test('default System resolves before DOM readiness and follows device changes',()=>{
 const q=setup({dark:true});assert.equal(q.root.dataset.theme,'dark');assert.equal(q.api.getPreference(),'system');
 q.system.matches=false;q.handlers.system();assert.equal(q.root.dataset.theme,'light');
});
test('explicit theme persists, ignores system changes and invalid values recover to System',()=>{
 const q=setup();q.api.setPreference('dark');assert.equal(q.stored(),'dark');q.handlers.system();assert.equal(q.root.dataset.theme,'dark');
 q.api.setPreference('unknown');assert.equal(q.api.getPreference(),'system');assert.equal(q.root.dataset.theme,'light');
});
test('storage denial never blocks rendering or changing the current page',()=>{
 const q=setup({blocked:true,dark:true});assert.equal(q.root.dataset.theme,'dark');q.api.setPreference('light');assert.equal(q.root.dataset.theme,'light');
});
test('storage events synchronize other tabs without rewriting their preference',()=>{
 const q=setup();q.external('dark');assert.equal(q.root.dataset.theme,'dark');assert.equal(q.api.getPreference(),'dark');
 q.external(null);assert.equal(q.api.getPreference(),'system');assert.equal(q.root.dataset.theme,'light');
});
test('printable documents remain light without replacing the saved preference',()=>{
 const q=setup({stored:'dark',dark:true,print:true});assert.equal(q.root.dataset.theme,'light');assert.equal(q.stored(),'dark');
});
function contrast(a,b){
 const lum=hex=>{const rgb=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;};
 const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
}
test('dark semantic text and input-border pairs retain readable contrast',()=>{
 const css=fs.readFileSync(path.join(__dirname,'../static/Reservation/css/tokens.css'),'utf8');
 const dark=css.slice(css.indexOf(":root[data-theme='dark']"));
 const tokens=Object.fromEntries([...dark.matchAll(/(--[a-z-]+):\s*(#[0-9a-f]{6});/g)].map(m=>[m[1],m[2]]));
 for(const kind of ['success','warning','info','complete','danger'])assert.ok(contrast(tokens[`--color-${kind}-text`],tokens[`--color-${kind}-surface`])>=4.5,kind);
 for(const name of ['--color-text','--color-text-muted','--color-primary-text'])assert.ok(contrast(tokens[name],tokens['--color-surface'])>=4.5,name);
 assert.ok(contrast('#ffffff',tokens['--color-primary'])>=4.5,'primary button');
 assert.ok(contrast(tokens['--color-border-strong'],tokens['--color-surface'])>=3,'input outline');
});
test('dashboard recreates charts with the new palette without changing data',()=>{
 const page=fs.readFileSync(path.join(__dirname,'../../templates/Reservation/admin/dashboard/AdminDashboard.html'),'utf8');
 const script=page.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
 const handlers={},instances={};let destroyed=0,next=0,dark=false;
 const nodes={monthlyBookingChart:{id:'monthlyBookingChart',setAttribute:()=>{}},facilityUsageChart:{id:'facilityUsageChart',setAttribute:()=>{}}};
 for(const [id,data] of [['monthly-labels-data',['Oct']],['monthly-bookings-data',[3]],['facility-labels-data',['Room']],['facility-usage-data',[2]]])nodes[id]={textContent:JSON.stringify(data)};
 class Chart{static instances=instances;static defaults={font:{},animation:{},transitions:{active:{animation:{}}}};
  static getChart(canvas){return Object.values(instances).find(c=>c.canvas===canvas);}
  constructor(canvas,config){this.id=++next;this.canvas=canvas;this.config=config;this.data=config.data;this.options=config.options;instances[this.id]=this;}
  destroy(){destroyed++;delete instances[this.id];}}
 const colors=()=>({'--color-chart-primary':dark?'#e5a19a':'#621515','--color-text-muted':dark?'#bfb6be':'#626262','--duration-chart':'320ms','--duration-fast':'140ms'});
 vm.runInNewContext(script,{Chart,document:{documentElement:{},getElementById:id=>nodes[id],addEventListener:(name,fn)=>handlers[name]=fn},getComputedStyle:()=>({getPropertyValue:name=>colors()[name]||'#ffffff'}),matchMedia:()=>({matches:false,addEventListener:()=>{}})});
 handlers.DOMContentLoaded();assert.equal(Object.keys(instances).length,2);assert.equal(Chart.getChart(nodes.monthlyBookingChart).data.datasets[0].backgroundColor,'#621515');
 dark=true;handlers['spasyo:theme-change']();assert.equal(destroyed,2);assert.equal(Object.keys(instances).length,2);
 const chart=Chart.getChart(nodes.monthlyBookingChart);assert.equal(chart.data.datasets[0].backgroundColor,'#e5a19a');assert.equal(chart.data.datasets[0].data[0],3);assert.equal(chart.options.animation,false);
});
