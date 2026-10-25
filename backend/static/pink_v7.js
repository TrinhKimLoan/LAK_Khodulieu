/* Enhance restored V5 prediction form with consistent price; this executes after V6. */
(function(){
 const previousBind=bindControls;
 bindControls=function(){previousBind();const form=document.getElementById('v5PredictionForm');if(!form)return;
 const product=form.querySelector('[name="product_id"]'), qty=form.querySelector('[name="quantity"]'),amount=form.querySelector('[name="goods_amount"]');
 if(!product||!qty||!amount)return;
 amount.readOnly=true;amount.style.background='#fff0f6';amount.title='Tự động tính: đơn giá trong Dim_Product × số lượng';
 const label=amount.closest('label');if(label){label.firstChild.textContent='Giá trị hàng (tự tính, VND)';let hint=document.createElement('small');hint.style.cssText='display:block;color:#9b7184;font-size:10px;margin-top:4px';hint.textContent='Giá tham chiếu sản phẩm × số lượng';label.append(hint);}
 let priceMap=new Map();
 function update(){const row=priceMap.get(product.value),q=Number(qty.value);amount.value=row&&row.unit_price!=null&&q>0?String(Math.round(row.unit_price*q)):'';const submit=form.querySelector('button[type="submit"]');if(submit)submit.disabled=!amount.value;}
 product.addEventListener('change',update);qty.addEventListener('input',update);
 fetch('/api/v1/products/unit-prices',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{priceMap=new Map(d.items.map(x=>[x.product_id,x]));if(product){[...product.options].forEach(opt=>{let x=priceMap.get(opt.value);if(x)opt.textContent=(x.product_name||x.product_id)+' ('+opt.value+')';});}update()}).catch(e=>{const t=document.getElementById('v5PredictionResult');if(t)t.textContent='Chưa lấy được bảng giá sản phẩm; kiểm tra /api/v1/products/unit-prices. '+e.message;});
 };
})();
