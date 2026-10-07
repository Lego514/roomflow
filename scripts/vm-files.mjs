import http from 'node:http';
import fs from 'node:fs';
const server = http.createServer(async (req,res) => {
  if(req.method==='GET' && req.url==='/lab.tar') {
    res.writeHead(200,{'Content-Type':'application/x-tar'}); fs.createReadStream('.runtime/lab.tar').pipe(res); return;
  }
  if(req.method==='PUT' && req.url==='/results.tar') {
    const stream=fs.createWriteStream('.runtime/linux-results.tar');
    let bytes=0;
    try {
      for await(const chunk of req) {
        bytes+=chunk.length;
        if(bytes>100*1024*1024) throw new Error('Export too large');
        if(!stream.write(chunk)) await new Promise(resolve=>stream.once('drain',resolve));
      }
      await new Promise(resolve=>stream.end(resolve)); res.writeHead(200); res.end('Saved');
    } catch(error) { stream.destroy();res.writeHead(400);res.end(error.message); }
    return;
  }
  res.writeHead(404);res.end('Not found');
});
server.listen(3211,'127.0.0.1',()=>console.log('VM artifact bridge on loopback3211'));
