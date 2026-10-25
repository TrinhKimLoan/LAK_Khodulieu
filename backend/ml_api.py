"""Read exported ML experiments; no online training and no fabricated results."""
from pathlib import Path
import csv, os
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix='/api/v1/ml', tags=['Machine Learning'])
ROOT=Path(os.getenv('ML_OUTPUT_DIR','/srv/ml_outputs'))

def rows(group, filename):
    path=ROOT/group/filename
    if not path.is_file():
        return []
    with path.open('r', encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def convert(row):
    output={}
    for k,v in row.items():
        if k is None: continue
        if v is None or v=='': output[k]=None;continue
        try: output[k]=float(v) if any(a in v.lower() for a in ['.','e']) else int(v)
        except (ValueError,TypeError):output[k]=v
    return output

def require(items, path):
    if not items:raise HTTPException(503, detail=f'Chưa có kết quả ML: {path}. Hãy chạy cell SAVE trong notebook, rồi copy outputs/nb/... vào backend/ml_outputs/...')
    return items

@router.get('/status')
def status():
    names={'ml1':['ml1_customer_segments.csv','ml1_cluster_summary.csv','ml1_k_selection.csv'], 'ml2':['ml2_model_comparison.csv','ml2_feature_importance.csv','ml2_model.joblib'], 'ml3':['ml3_metrics_A_leave_last_out.csv','ml3_metrics_B_temporal.csv','ml3_category_cooccurrence.csv']}
    return {group:{name:(ROOT/group/name).exists() for name in files} for group,files in names.items()}

@router.get('/customers/segments')
def segments(limit:int=Query(40,ge=1,le=300),offset:int=Query(0,ge=0),cluster_id:int|None=None):
    data=require(rows('ml1','ml1_customer_segments.csv'),'ml1/ml1_customer_segments.csv')
    filtered=[convert(r) for r in data]
    if cluster_id is not None:filtered=[r for r in filtered if r.get('cluster_id')==cluster_id]
    return {'total':len(filtered),'items':filtered[offset:offset+limit],'note':'RFM/K-Means trained on full data period; date selection on other dashboard pages does not recalculate the model.'}

@router.get('/customers/summary')
def cluster_summary():
    d=require(rows('ml1','ml1_cluster_summary.csv'),'ml1/ml1_cluster_summary.csv')
    return {'items':[convert(x) for x in d],'k_selection':[convert(x) for x in rows('ml1','ml1_k_selection.csv')]}

@router.get('/shipping/evaluation')
def shipping_evaluation():
    d=require(rows('ml2','ml2_model_comparison.csv'),'ml2/ml2_model_comparison.csv')
    return {'models':[convert(x) for x in d], 'feature_importance':[convert(x) for x in rows('ml2','ml2_feature_importance.csv')], 'note':'Notebook concludes group-mean shipping_type baseline outperforms full Random Forest; no claim RF is best.'}

class ShippingInput(BaseModel):
    product_id:str
    shipping_type:str
    district:str
    warehouse:str
    vehicle:str
    city:str='TP.HCM'
    quantity:int=Field(ge=1)
    goods_amount:float=Field(ge=0)
    pack_month:int=Field(ge=1,le=12)
    pack_dow:int=Field(ge=0,le=6)

@router.post('/shipping/predict')
def shipping_predict(item:ShippingInput):
    path=ROOT/'ml2'/'ml2_model.joblib'
    if not path.is_file():raise HTTPException(503,'Chưa có ml2_model.joblib; xuất từ ML2 notebook trước.')
    try:
        import joblib, pandas as pd
        model=joblib.load(path)  # Load ONLY trusted artifacts from group member
        frame=pd.DataFrame([{k:getattr(item,k) for k in model['features']}])
        y=float(model['pipeline'].predict(frame)[0])
        return {'delivery_days_predicted':round(y,2),'model_version':model.get('model_version'),'warning':'Dữ liệu mô phỏng; RF chưa vượt baseline trung bình theo loại giao hàng trên test 2025.'}
    except KeyError as exc:
        raise HTTPException(422,f'Model expects a missing feature: {str(exc)}') from exc
    except Exception as exc:
        raise HTTPException(503,f'Không tải/dự đoán được model ML2: {type(exc).__name__}. Kiểm tra phiên bản scikit-learn và các cột feature.') from exc

@router.get('/recommendations/evaluation')
def recommender_evaluation():
    d={}
    for protocol in ('A_leave_last_out','B_temporal'):
        d[protocol]=[convert(x) for x in rows('ml3',f'ml3_metrics_{protocol}.csv')]
    if not any(d.values()):raise HTTPException(503,'Chưa có file đánh giá ML3 ở ml_outputs/ml3')
    return {'protocols':d,'category_cooccurrence':[convert(x) for x in rows('ml3','ml3_category_cooccurrence.csv')[:25]],'conclusion':'Không thuật toán gợi ý nào vượt baseline MostPopular/Random trên cả hai giao thức; không triển khai gợi ý cá nhân hóa như chức năng đã xác thực.'}
