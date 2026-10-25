const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../static/Reservation/js/help-tips.js'),'utf8');
function setup(){
 const handlers={},attrs={};let open=false,focus=0,created=0;
 const content={};
 const text={nodeType:3,textContent:'Keep this on to make the item available.'};
 const source={nodeType:1,childNodes:[text]};
 const trigger={setAttribute:(k,v)=>attrs[k]=v,removeAttribute:k=>delete attrs[k],closest:()=>null,
  parentElement:{querySelector:()=>source},getBoundingClientRect:()=>({left:360,right:384,top:200,bottom:224,width:24,height:24}),focus:()=>focus++};
 const popup={get textContent(){return content.textContent;},append:()=>{},style:{setProperty:()=>{}},setAttribute:()=>{},addEventListener:()=>{},matches:()=>open,showPopover:()=>open=true,hidePopover:()=>open=false,
  contains:node=>node===popup,getBoundingClientRect:()=>({width:240,height:48})};
 class Element{} Element.prototype.showPopover=()=>{};
 vm.runInNewContext(code,{HTMLElement:Element,document:{querySelector:()=>({getAttribute:()=>'/icons.svg#info'}),querySelectorAll:()=>[],createElement:()=>++created===1?popup:content,body:{append:()=>{}},
  addEventListener:(name,fn)=>handlers[name]=fn},window:{addEventListener:()=>{}},innerWidth:390,innerHeight:740});
 const click=(target=trigger)=>handlers.click({target:target===trigger?{closest:()=>trigger}:target===popup?{closest:()=>null}: {closest:()=>null},preventDefault:()=>{}});
 return {click,handlers,attrs,popup,text,isOpen:()=>open,focus:()=>focus};
}
test('help opens on click and the same button closes it without reopening',()=>{
 const q=setup();q.click();assert.equal(q.isOpen(),true);assert.equal(q.attrs['aria-expanded'],'true');
 q.click();assert.equal(q.isOpen(),false);assert.equal(q.attrs['aria-expanded'],'false');assert.equal(q.attrs['aria-describedby'],undefined);
});
test('outside clicks dismiss help and a later opening reads current guidance',()=>{
 const q=setup();q.click();q.click(null);assert.equal(q.isOpen(),false);
 q.text.textContent='Updated guidance from the next form.';q.click();assert.equal(q.popup.textContent,'Updated guidance from the next form.');
 assert.ok(parseFloat(q.popup.style.left)>=8);assert.ok(parseFloat(q.popup.style.left)+240<=382);
});
test('Escape dismisses help, restores focus and prevents dismissal of its parent dialog',()=>{
 const q=setup();q.click();let prevented=false,stopped=false;
 q.handlers.keydown({key:'Escape',preventDefault:()=>prevented=true,stopImmediatePropagation:()=>stopped=true});
 assert.equal(q.isOpen(),false);assert.equal(q.focus(),1);assert.equal(prevented,true);assert.equal(stopped,true);
});
