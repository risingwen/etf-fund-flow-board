/* 公共读取器：发布清单和内容哈希一致才交给页面，避免部署中混用版本。 */
window.VerifiedData = (() => {
  const text = async path => {
    const r = await fetch(path, {cache:'no-store',signal:AbortSignal.timeout(30000)});
    if (!r.ok) throw Error('数据读取失败 '+r.status);
    return r.text();
  };
  const manifest = async () => JSON.parse(await text('./history-manifest.json?t='+Date.now()));
  const file = async (name, hash) => {
    if (!/^[a-f0-9]{64}$/.test(hash||'')) throw Error('发布清单缺少校验记录');
    const source=await text('./'+name+'?v='+hash);
    const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(source));
    const actual=[...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('');
    if(actual!==hash) throw Error('发布文件版本尚未一致，保留当前画面');
    return JSON.parse(source);
  };
  const bundle=async (names,m) => Object.fromEntries(await Promise.all(names.map(async n=>[n,await file(n,m.files[n])])));
  return {manifest,file,bundle};
})();
