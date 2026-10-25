/* V6: simplify ML interpretations and stabilize on-demand health UI. */
(function(){
const originalShipping=shipping, originalProducts=products, originalMonitor=monitor;
const dom=html=>{const node=document.createElement('div');node.innerHTML=html;return node};
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
shipping=async function(){const root=dom(await originalShipping());
 // A model can predict, but current standalone form lets visitors type inconsistent pricing.
 // V7: retain ML2 interactive prediction form.
 root.querySelectorAll('.panel').forEach(p=>{const title=p.querySelector('.panel-title')?.textContent||'';
 if(title.includes('Thời gian giao theo kho')){
 const items=[...p.querySelectorAll('.bar-row')].map(r=>({label:r.querySelector('.bar-row-label')?.textContent.trim()||'',time:r.querySelector('.bar-value')?.textContent.trim()||''}));
 if(items.length){p.querySelector('.panel-subtitle')?.replaceChildren(document.createTextNode('Thời gian trung bình từ khi đóng gói tới khi nhận; mọi đơn đều giao tại TP.HCM'));
 p.querySelector('.chart-area')?.remove();
 const area=p.querySelector('.v5-compact-bars')||p.querySelector('.bar-row')?.parentElement;
 if(area)area.outerHTML='<div class="table-scroll"><table class="v6-warehouse-table"><thead><tr><th>Kho xuất hàng</th><th>Thời gian giao trung bình</th></tr></thead><tbody>'+items.map(x=>'<tr><td>'+safe(x.label)+'</td><td>'+safe(x.time)+'</td></tr>').join('')+'</tbody></table></div>';}}
 if(title.includes('Hiểu kết quả đánh giá giao hàng')){
 const explanations=p.querySelector('.v5-metric-cards');if(explanations)explanations.innerHTML='<div><b>MAE · Sai lệch trung bình</b><span>Mô hình dự đoán lệch thực tế bao nhiêu ngày cho mỗi đơn, tính trung bình. Số ngày sai lệch càng ít thì càng tốt.</span></div><div><b>RMSE · Sai lệch có phạt lỗi lớn</b><span>Cũng đo bằng ngày, nhưng những đơn dự đoán sai rất nhiều sẽ bị phạt mạnh hơn.</span></div><div><b>R² · Mức độ giải thích</b><span>So sánh khả năng dự đoán với cách luôn dùng thời gian giao trung bình. Gần 1 tốt; dưới 0 là kém hơn cách đoán trung bình.</span></div>';
 }
 });return root.innerHTML;
};
products=async function(){let root=dom(await originalProducts());const target=[...root.querySelectorAll('.panel')].find(p=>(p.querySelector('.panel-title')?.textContent||'').includes('Mô hình nào tìm đúng sản phẩm tiếp theo?'));
 if(target){target.querySelector('.panel-title').textContent='Đánh giá khả năng gợi ý từ lịch sử mua';let ps=target.querySelectorAll('p');if(ps[0])ps[0].textContent='Đây là thử nghiệm offline: nhóm che bớt giao dịch đã có rồi kiểm tra hệ thống có gợi ý đúng sản phẩm được giữ lại không. Không có nghĩa web hiện đang dự đoán chắc chắn đơn mua tiếp theo của từng khách.';}
 return root.innerHTML;
};
monitor=async function(){let root=dom(await originalMonitor());let old=root.querySelector('#v5Health');if(old)old.remove();
 const panel=`<section class="panel" id="v6Health"><div class="panel-header"><div><div class="panel-title">Kiểm tra tình trạng nguồn</div><div class="panel-subtitle">Kiểm tra thủ công; trạng thái không thay thế giám sát định kỳ Airflow</div></div><button type="button" class="btn btn-primary" id="v6HealthButton">↻ Kiểm tra ngay</button></div><div id="v6HealthResults" class="v5-health-grid"><div class="v6-health-status">PostgreSQL · Chưa kiểm tra</div><div class="v6-health-status">6 file Excel · Chưa kiểm tra</div><div class="v6-health-status">Media Cloud · Chưa kiểm tra</div></div><div class="v6-health-meta" id="v6HealthMeta">Không gọi Media Cloud Search API; chỉ kiểm tra khả năng truy cập website.</div><details class="v6-health-meta"><summary>Khi nguồn gặp sự cố thì làm gì?</summary><p>Airflow ghi nhận lỗi và cảnh báo theo webhook nếu được cấu hình. Dữ liệu DWH hiện có vẫn phục vụ dashboard; job nhập dữ liệu mới cần retry theo giới hạn/backoff. Nếu nguồn chưa phục hồi, hiển thị thời điểm cập nhật cuối và không báo dữ liệu đang mới.</p></details></section>`;
 return panel+root.innerHTML;
};
const bindOld=bindControls;
bindControls=function(){bindOld();const btn=document.getElementById('v6HealthButton');if(!btn)return;
 btn.addEventListener('click',async()=>{const out=document.getElementById('v6HealthResults'),meta=document.getElementById('v6HealthMeta');btn.disabled=true;out.innerHTML='<div class="v6-health-status">Đang kiểm tra ba nguồn...</div>';
 try{const response=await fetch('/api/v1/pipeline/health-check-v6',{method:'POST',headers:{'X-Requested-With':'EcomInsight','Accept':'application/json'},credentials:'same-origin',cache:'no-store'});
 const payload=await response.text();let body;try{body=JSON.parse(payload)}catch{throw Error('Backend trả về HTTP '+response.status+' nhưng không có JSON. Xem docker logs api; có thể backend chưa build lại hoặc bị lỗi server.')}if(!response.ok)throw Error(body.detail||'HTTP '+response.status);
 out.innerHTML=body.sources.map(x=>`<div class="v6-health-status"><strong>${safe(x.name)}</strong><span class="${safe(x.status)}">${x.status==='healthy'?'Hoạt động':x.status==='reachable'?'Có phản hồi':'Không khả dụng'}</span><div>${safe(x.detail)}</div>${x.latency_ms!=null?`<small>${safe(x.latency_ms)} ms</small>`:''}</div>`).join('');
 meta.textContent=(body.cached?'Dữ liệu kiểm tra được lưu trong 60 giây · ':'')+'Kiểm tra: '+new Date(body.checked_at).toLocaleString('vi-VN')+' · Media Cloud mới kiểm tra truy cập website, không phải xác thực API key.';
 }catch(e){out.innerHTML='<div class="v6-failure">Kiểm tra không thành công: '+safe(e.message)+'</div>';meta.textContent='Mở /docs hoặc docker logs api để xem nguyên nhân.'}finally{btn.disabled=false;}});
};
})();
