// Isolated rendered fixtures; never sends requests to a production Adapter.
const { chromium } = require('playwright');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
 const root = process.argv[2];
 assert(root.includes('/runtime/r6x-network-select-'));
 const fixtures = Object.fromEntries(fs.readdirSync(root).filter(f=>f.endsWith('.json')).map(f=>[f.slice(0,-5), JSON.parse(fs.readFileSync(path.join(root,f)))]));
 let mode='proxy'; const posts=[];
 const server=http.createServer((req,res)=>{
  if(req.method==='POST'){
   let body='';req.on('data',d=>body+=d);req.on('end',()=>{posts.push({path:req.url,values:Object.fromEntries(new URLSearchParams(body))});res.writeHead(303,{Location:'/manage/'});res.end();});
  }else{res.writeHead(200,fixtures[mode].headers);res.end(fixtures[mode].body);}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try {
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const results=[];
  for(const width of [1280,768,390]){
   const context=await browser.newContext({viewport:{width,height:900},javaScriptEnabled:false});
   const page=await context.newPage();
   for(mode of ['proxy','direct','missing','disabled','ungranted','running','long-label']){
    await page.goto(`http://127.0.0.1:${server.address().port}/manage/`);
    await page.getByText('网络配置（停止后应用）',{exact:true}).click();
    const select=page.locator('#network-selection-personal');
    const form=page.locator('form').filter({has:select});
    assert.equal(await form.count(),1);assert.equal(await form.locator('select').count(),1);assert.equal(await form.locator('button').count(),1);
    const expected=mode==='direct'?'direct':['missing','disabled','ungranted'].includes(mode)?'':'proxy|corp|2';
    assert.equal(await select.inputValue(),expected);
    assert.equal(await form.getByRole('button',{name:'应用网络'}).isDisabled(),mode==='running');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth)<=width+1,`overflow ${width}/${mode}`);
    const box=await form.boundingBox();assert(box.width<=width);
    if(mode==='long-label'||mode==='proxy')await page.screenshot({path:path.join(root,`${mode}-${width}.png`),fullPage:true});
    if(mode==='proxy'){
     await select.focus(); await page.keyboard.press('ArrowDown');
     assert.equal(await select.inputValue(),'proxy|corp|3');
     await form.locator('[name=idempotency_key]').fill('qa-change-1');
     await form.getByRole('button',{name:'应用网络'}).click();
     const post=posts.at(-1);assert.equal(post.path,'/manage/browsers/personal');assert.equal(post.values.action,'network_select');assert.equal(post.values.network_selection,'proxy|corp|3');assert.equal(post.values.revision,'3');assert.equal(post.values.idempotency_key,'qa-change-1');assert('csrf' in post.values);
    }
    results.push({width,mode,pass:true});
   }
   await context.close();
  }
  fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({results,submissions:posts.length,javascript:false},null,2));
  console.log(`PASS ${results.length} viewport/state checks; ${posts.length} native form submissions with JavaScript disabled`);
 } finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
