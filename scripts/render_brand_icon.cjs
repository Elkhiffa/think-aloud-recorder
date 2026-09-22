// Regenerate the native icon from the same SVG used by the application.
// Uses an existing Playwright/Edge setup; never downloads a browser or package.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const path=require('node:path');
const fs=require('node:fs');
const {pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:256,height:256},deviceScaleFactor:1});
  await page.goto(pathToFileURL(path.resolve(__dirname,'../ui/brand.svg')).href);
  const sizes=[16,24,32,48,64,128,256],images=[];
  for(const size of sizes){
   await page.setViewportSize({width:size,height:size});
   images.push(await page.screenshot({omitBackground:true}));
  }
  // Windows Vista+ supports PNG-backed ICO entries; no extra imaging dependency.
  const header=Buffer.alloc(6+16*sizes.length);header.writeUInt16LE(1,2);header.writeUInt16LE(sizes.length,4);
  let offset=header.length;
  images.forEach((data,index)=>{const pos=6+16*index;header[pos]=sizes[index]%256;header[pos+1]=sizes[index]%256;header.writeUInt16LE(1,pos+4);header.writeUInt16LE(32,pos+6);header.writeUInt32LE(data.length,pos+8);header.writeUInt32LE(offset,pos+12);offset+=data.length;});
  fs.writeFileSync(path.resolve(__dirname,'../ui/brand.ico'),Buffer.concat([header,...images]));
  const work=path.resolve(__dirname,'../work');fs.mkdirSync(work,{recursive:true});
  fs.writeFileSync(path.join(work,'brand-256.png'),images[6]);
  console.log('Rendered native icon sizes: '+sizes.join(', '));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
