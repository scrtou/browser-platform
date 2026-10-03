// Use isolated Go-rendered pages and a local submission receiver.
const {chromium}=require('playwright'),fs=require('node:fs'),http=require('node:http'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=process.argv[2];assert(root.includes('/runtime/r6y-management-delete-'));
 const fixtures={};for(const key of ['fingerprints','displays','combinations','network','accounts'])fixtures[key]=JSON.parse(fs.readFileSync(path.join(root,key+'.json')));
 let mode='fingerprints';const posts=[];
 const server=http.createServer((req,res)=>{if(req.method==='POST'){let body='';req.on('data',d=>body+=d);req.on('end',()=>{posts.push({path:req.url,form:Object.fromEntries(new URLSearchParams(body))});res.writeHead(303,{Location:'/manage/'});res.end()})}else{res.writeHead(200,fixtures[mode].headers);res.end(fixtures[mode].body)}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
 try{
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
  for(const width of [1280,768,390]){
   const context=await browser.newContext({viewport:{width,height:900},javaScriptEnabled:false});const page=await context.newPage();
   for(mode of Object.keys(fixtures)){
    await page.goto(`http://127.0.0.1:${server.address().port}/manage/`);
    assert(await page.locator('.delete-form').count()>0,mode);
    if(mode==='displays')assert.equal(await page.locator('form[action*="display-auto/delete"]').count(),0);
    if(mode==='accounts')assert.equal(await page.locator('form[action="/manage/accounts/bob"]').filter({has:page.locator('input[value=delete]')}).count(),0);
    const count=mode==='combinations'?2:1;
    for(let i=0;i<count;i++){
     const detail=mode==='combinations'?page.locator(i===0?'.jobs-table .delete-control':'.accepted-combinations .delete-control').first():page.locator('.delete-control').first();
     await detail.locator('summary').click();
     const form=detail.locator('.delete-form');
     const before=posts.length;await form.locator('button').click();assert.equal(posts.length,before,'confirmation was bypassed');
     await form.getByRole('checkbox',{name:'确认删除'}).check();
     assert(await page.evaluate(()=>document.documentElement.scrollWidth)<=width+1,`overflow ${mode}/${width}`);
     if(i===0)await page.screenshot({path:path.join(root,`${mode}-${width}.png`),fullPage:true});
     await form.locator('button').click();assert.equal(posts.length,before+1);
     assert.equal(posts.at(-1).form.confirm,'delete');assert('csrf' in posts.at(-1).form);
    }
    results.push({width,mode,pass:true});
   }
   await context.close();
  }
  fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({results,submissions:posts.length,javascript:false},null,2));console.log(`PASS ${results.length} layout checks; ${posts.length} confirmed submissions; unconfirmed forms blocked`);
 }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve))}
})().catch(e=>{console.error(e);process.exitCode=1});
