import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import (
    engine,
    get_db,
    Base,
    BroilerBatch,
    FarmTransaction,
    DailyFeedLog,
    DailyLog,
    VaccineLog
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Poultry Farm Management System")

# --- Schemas ---
class BatchCreate(BaseModel):
    name: str
    initial_count: int
    chick_price: float

class MortalityLogCreate(BaseModel):
    batch_id: int
    dead_birds: int

class FeedLogCreate(BaseModel):
    batch_id: int
    feed_type: str
    bags_consumed: float
    bag_price: float

class VaccineLogCreate(BaseModel):
    batch_id: int
    vaccine_name: str
    cost: float

class ExpenseLogCreate(BaseModel):
    batch_id: int
    amount: float
    description: str

class BatchSaleCreate(BaseModel):
    batch_id: int
    total_weight_kg: float
    price_per_kg: float


# --- API Endpoints ---
@app.post("/api/batches")
def create_batch(batch: BatchCreate, db: Session = Depends(get_db)):
    try:
        new_batch = BroilerBatch(
            name=batch.name,
            initial_count=batch.initial_count,
            chick_price=batch.chick_price,
            start_date=datetime.now()
        )
        db.add(new_batch)
        db.commit()
        db.refresh(new_batch)

        chicks_cost = batch.initial_count * batch.chick_price
        if chicks_cost > 0:
            tx = FarmTransaction(
                batch_id=new_batch.id,
                amount=chicks_cost,
                description=f"شراء كتاكيت ({batch.initial_count} كتكوت × {batch.chick_price} ج.س)"
            )
            db.add(tx)
            db.commit()

        return {"status": "success", "batch_id": new_batch.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/mortality")
def record_mortality(log: MortalityLogCreate, db: Session = Depends(get_db)):
    new_log = DailyLog(batch_id=log.batch_id, dead_birds=log.dead_birds, avg_weight=0.0)
    db.add(new_log)
    db.commit()
    return {"status": "success"}

@app.post("/api/feed")
def record_feed(log: FeedLogCreate, db: Session = Depends(get_db)):
    new_log = DailyFeedLog(
        batch_id=log.batch_id,
        feed_type=log.feed_type,
        bags_consumed=log.bags_consumed,
        bag_price=log.bag_price
    )
    db.add(new_log)
    
    feed_cost = log.bags_consumed * log.bag_price
    if feed_cost > 0:
        tx = FarmTransaction(
            batch_id=log.batch_id,
            amount=feed_cost,
            description=f"استهلاك علف ({log.feed_type}) - {log.bags_consumed} شوال × {log.bag_price} ج.س"
        )
        db.add(tx)

    db.commit()
    return {"status": "success"}

@app.post("/api/vaccines")
def record_vaccine(log: VaccineLogCreate, db: Session = Depends(get_db)):
    new_vac = VaccineLog(
        batch_id=log.batch_id,
        vaccine_name=log.vaccine_name,
        cost=log.cost
    )
    db.add(new_vac)
    
    if log.cost > 0:
        tx = FarmTransaction(
            batch_id=log.batch_id,
            amount=log.cost,
            description=f"لقاحات وفاكسينات: {log.vaccine_name}"
        )
        db.add(tx)

    db.commit()
    return {"status": "success"}

@app.post("/api/expenses")
def record_expense(log: ExpenseLogCreate, db: Session = Depends(get_db)):
    new_tx = FarmTransaction(batch_id=log.batch_id, amount=log.amount, description=log.description)
    db.add(new_tx)
    db.commit()
    return {"status": "success"}

@app.post("/api/sales")
def create_sale(sale: BatchSaleCreate, db: Session = Depends(get_db)):
    total_amount = sale.total_weight_kg * sale.price_per_kg
    new_tx = FarmTransaction(
        batch_id=sale.batch_id,
        amount=-total_amount,
        description=f"إيراد بيع: {sale.total_weight_kg} كجم × {sale.price_per_kg} ج.س"
    )
    db.add(new_tx)
    db.commit()
    return {"status": "success"}

@app.get("/api/analytics")
def get_analytics(batch_id: Optional[int] = None, db: Session = Depends(get_db)):
    all_batches = db.query(BroilerBatch).order_by(BroilerBatch.id.asc()).all()

    if not all_batches:
        return {
            "batches_list": [], "selected_batch_id": None, "initial_birds": 0, "chick_price": 0.0,
            "chicks_cost": 0.0, "live_birds": 0, "total_feed_bags": 0, "feed_cost": 0.0,
            "feed_breakdown": {}, "total_expenses": 0.0, "total_revenue": 0.0, "net_profit": 0.0,
            "total_deaths": 0, "mortality_rate": "0%", "fcr": 0.0, "diesel_cost": 0.0, "vaccine_cost": 0.0, "vaccines_list": []
        }

    batches_list = [{"id": b.id, "name": b.name or f"دفعة #{b.id}"} for b in all_batches]

    if batch_id:
        selected_batches = [b for b in all_batches if b.id == batch_id]
        sel_batch = selected_batches[0] if selected_batches else all_batches[-1]
    else:
        sel_batch = all_batches[-1]

    b_id = sel_batch.id
    initial_birds = sel_batch.initial_count or 0
    chick_price = sel_batch.chick_price or 0.0
    chicks_cost = initial_birds * chick_price
    
    daily_logs = db.query(DailyLog).filter(DailyLog.batch_id == b_id).all()
    total_deaths = sum([d.dead_birds for d in daily_logs if d.dead_birds]) or 0
    live_birds = max(initial_birds - total_deaths, 0)
    mortality_rate = round((total_deaths / initial_birds * 100), 2) if initial_birds > 0 else 0.0

    feed_logs = db.query(DailyFeedLog).filter(DailyFeedLog.batch_id == b_id).all()
    total_feed_bags = sum([f.bags_consumed for f in feed_logs if f.bags_consumed]) or 0
    feed_cost = sum([(f.bags_consumed or 0) * (f.bag_price or 0) for f in feed_logs]) or 0.0
    
    # تفصيل أنواعه
    feed_breakdown = {"ماسكر": 0.0, "بادي": 0.0, "نامي": 0.0, "ناهي": 0.0}
    for f in feed_logs:
        ftype = f.feed_type or "بادي"
        feed_breakdown[ftype] = feed_breakdown.get(ftype, 0.0) + (f.bags_consumed or 0.0)

    total_feed_kg = total_feed_bags * 50
    fcr = round(total_feed_kg / (live_birds * 1.8), 2) if live_birds > 0 else 0.0

    vaccine_logs = db.query(VaccineLog).filter(VaccineLog.batch_id == b_id).all()
    vaccine_cost = sum([v.cost for v in vaccine_logs if v.cost]) or 0.0
    vaccines_list = [{"id": v.id, "name": v.vaccine_name, "cost": v.cost, "date": v.log_date.strftime("%Y-%m-%d")} for v in vaccine_logs]

    transactions = db.query(FarmTransaction).filter(FarmTransaction.batch_id == b_id).all()
    total_expenses = sum([t.amount for t in transactions if t.amount > 0]) or 0.0
    total_revenue = abs(sum([t.amount for t in transactions if t.amount < 0])) or 0.0
    net_profit = total_revenue - total_expenses

    diesel_cost = sum([t.amount for t in transactions if t.amount > 0 and t.description and "ديزل" in t.description]) or 0.0

    return {
        "batches_list": batches_list,
        "selected_batch_id": b_id,
        "initial_birds": initial_birds,
        "chick_price": chick_price,
        "chicks_cost": chicks_cost,
        "live_birds": live_birds,
        "total_feed_bags": total_feed_bags,
        "feed_cost": feed_cost,
        "feed_breakdown": feed_breakdown,
        "total_expenses": float(total_expenses),
        "total_revenue": float(total_revenue),
        "net_profit": float(net_profit),
        "total_deaths": total_deaths,
        "mortality_rate": f"{mortality_rate}%",
        "fcr": fcr,
        "diesel_cost": diesel_cost,
        "vaccine_cost": vaccine_cost,
        "vaccines_list": vaccines_list
    }

@app.get("/api/admin/backup-db")
def backup_db():
    if os.path.exists(DB_PATH):
        return FileResponse(DB_PATH, filename="poultry_farm_backup.db")
    raise HTTPException(status_code=404, detail="Database file not found")


# --- Mobile UI ---
@app.get("/", response_class=HTMLResponse)
def mobile_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>اللوحة الميدانية</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <style>
            body { background-color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; }
            .btn-blue { background-color: #1d4ed8; color: #fff; border: none; font-weight: bold; border-radius: 12px; }
            .btn-blue:active { background-color: #1e40af !important; transform: scale(0.98); }
            .btn-outline-blue { border: 2px solid #1d4ed8; color: #1d4ed8; font-weight: bold; border-radius: 12px; background: #fff; }
            .card-custom { border-radius: 16px; border: 1px solid #e2e8f0; background: #fff; }
        </style>
    </head>
    <body class="p-3">
        <div class="container text-center" style="max-width: 480px;">
            <h4 class="fw-bold my-3 text-primary">🐓 اللوحة الميدانية للمزرعة</h4>
            
            <div class="card card-custom p-3 mb-3 text-start">
                <label class="form-label fw-bold text-secondary small mb-1">اختر الدفعة النشطة:</label>
                <select id="mBatchSelect" class="form-select fw-bold border-primary"></select>
            </div>

            <div class="card card-custom p-3 mb-3 d-grid gap-2">
                <button class="btn btn-blue p-3 fs-5" data-bs-toggle="modal" data-bs-target="#mortalityModal">☠️ تسجيل نافق</button>
                <button class="btn btn-blue p-3 fs-5" data-bs-toggle="modal" data-bs-target="#feedModal">🌾 تسجيل علف (تفصيلي)</button>
                <button class="btn btn-blue p-3 fs-5" data-bs-toggle="modal" data-bs-target="#vaccineModal">💉 تسجيل فاكسين / لقاح</button>
                <button class="btn btn-blue p-3 fs-5" data-bs-toggle="modal" data-bs-target="#expenseModal">💸 تسجيل مصروفات أخرى</button>
            </div>

            <a href="/owner" class="btn btn-outline-blue w-100 p-3 fs-6">👑 لوحة التحكم والتقارير</a>
        </div>

        <!-- Mortality Modal -->
        <div class="modal fade" id="mortalityModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content text-start">
                    <div class="modal-header"><h5 class="fw-bold">تسجيل النافق اليومي</h5></div>
                    <div class="modal-body">
                        <label class="form-label">عدد النافق (بالعدد):</label>
                        <input type="number" id="mDeadCount" class="form-control form-control-lg" placeholder="مثال: 5">
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
                        <button class="btn btn-primary fw-bold" onclick="submitMortality()">حفظ</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Feed Modal -->
        <div class="modal fade" id="feedModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content text-start">
                    <div class="modal-header"><h5 class="fw-bold">تسجيل استهلاك العلف</h5></div>
                    <div class="modal-body">
                        <label class="form-label">نوع العلف:</label>
                        <select id="mFeedType" class="form-select form-select-lg mb-3">
                            <option value="ماسكر">ماسكر (مركّز)</option>
                            <option value="بادي" selected>بادي (23%)</option>
                            <option value="نامي">نامي (21%)</option>
                            <option value="ناهي">ناهي (19%)</option>
                        </select>
                        <label class="form-label">عدد الأشوال المستهلكة:</label>
                        <input type="number" step="0.5" id="mFeedBags" class="form-control form-control-lg mb-3" placeholder="مثال: 2">
                        <label class="form-label">سعر الشوال الواحد (ج.س):</label>
                        <input type="number" id="mBagPrice" class="form-control form-control-lg" placeholder="مثال: 38000">
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
                        <button class="btn btn-primary fw-bold" onclick="submitFeed()">حفظ</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Vaccine Modal -->
        <div class="modal fade" id="vaccineModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content text-start">
                    <div class="modal-header"><h5 class="fw-bold">تسجيل فاكسين / لقاح جديد</h5></div>
                    <div class="modal-body">
                        <label class="form-label">اسم اللقاح / الفاكسين:</label>
                        <input type="text" id="mVaccineName" class="form-control form-control-lg mb-3" placeholder="مثال: نيوكاسل كولون / جمبورو">
                        <label class="form-label">إجمالي سعر / تكلفة الفاكسين (ج.س):</label>
                        <input type="number" id="mVaccineCost" class="form-control form-control-lg" placeholder="مثال: 25000">
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
                        <button class="btn btn-primary fw-bold" onclick="submitVaccine()">حفظ</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Expense Modal -->
        <div class="modal fade" id="expenseModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content text-start">
                    <div class="modal-header"><h5 class="fw-bold">تسجيل مصروف جديد</h5></div>
                    <div class="modal-body">
                        <label class="form-label">نوع المنصرف:</label>
                        <select id="mExpenseCategory" class="form-select mb-3">
                            <option value="شراء ديزل">⛽ شراء ديزل (وقود)</option>
                            <option value="شراء كهرباء">شراء كهرباء</option>
                            <option value="إصلاح عطل">إصلاح عطل</option>
                            <option value="ميز عمال">ميز عمال</option>
                            <option value="سلفية عمال">سلفية عمال</option>
                            <option value="رواتب عمال">رواتب عمال</option>
                            <option value="آخر">آخر</option>
                        </select>
                        <label class="form-label">المبلغ (بالجنيه السوداني):</label>
                        <input type="number" id="mExpenseAmount" class="form-control form-control-lg" placeholder="مثال: 15000">
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
                        <button class="btn btn-primary fw-bold" onclick="submitExpense()">حفظ</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            async function loadBatches() {
                try {
                    const res = await fetch('/api/analytics');
                    const data = await res.json();
                    const select = document.getElementById('mBatchSelect');
                    if (data.batches_list && data.batches_list.length > 0) {
                        select.innerHTML = data.batches_list.map(b => 
                            `<option value="${b.id}" ${b.id === data.selected_batch_id ? 'selected' : ''}>${b.name}</option>`
                        ).join('');
                    } else {
                        select.innerHTML = '<option value="">لا توجد دفعات حالياً</option>';
                    }
                } catch(e) { console.log("خطأ في التحميل"); }
            }

            async function submitMortality() {
                const batchId = document.getElementById('mBatchSelect').value;
                const deaths = document.getElementById('mDeadCount').value;
                if (!batchId || !deaths) return;
                await fetch('/api/mortality', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ batch_id: parseInt(batchId), dead_birds: parseInt(deaths) })
                });
                alert("✅ تم حفظ النافق!");
                document.getElementById('mDeadCount').value = '';
                bootstrap.Modal.getInstance(document.getElementById('mortalityModal')).hide();
            }

            async function submitFeed() {
                const batchId = document.getElementById('mBatchSelect').value;
                const feedType = document.getElementById('mFeedType').value;
                const bags = document.getElementById('mFeedBags').value;
                const price = document.getElementById('mBagPrice').value;
                if (!batchId || !bags) return;
                await fetch('/api/feed', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ batch_id: parseInt(batchId), feed_type: feedType, bags_consumed: parseFloat(bags), bag_price: parseFloat(price || 0) })
                });
                alert("✅ تم حفظ سحب العلف!");
                document.getElementById('mFeedBags').value = '';
                document.getElementById('mBagPrice').value = '';
                bootstrap.Modal.getInstance(document.getElementById('feedModal')).hide();
            }

            async function submitVaccine() {
                const batchId = document.getElementById('mBatchSelect').value;
                const vName = document.getElementById('mVaccineName').value;
                const vCost = document.getElementById('mVaccineCost').value;
                if (!batchId || !vName) return;
                await fetch('/api/vaccines', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ batch_id: parseInt(batchId), vaccine_name: vName.trim(), cost: parseFloat(vCost || 0) })
                });
                alert("✅ تم تسجيل الفاكسين بنجاح!");
                document.getElementById('mVaccineName').value = '';
                document.getElementById('mVaccineCost').value = '';
                bootstrap.Modal.getInstance(document.getElementById('vaccineModal')).hide();
            }

            async function submitExpense() {
                const batchId = document.getElementById('mBatchSelect').value;
                const category = document.getElementById('mExpenseCategory').value;
                const amount = document.getElementById('mExpenseAmount').value;
                if (!batchId || !amount) return;
                await fetch('/api/expenses', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ batch_id: parseInt(batchId), amount: parseFloat(amount), description: category })
                });
                alert("✅ تم حفظ المصروف!");
                document.getElementById('mExpenseAmount').value = '';
                bootstrap.Modal.getInstance(document.getElementById('expenseModal')).hide();
            }

            loadBatches();
        </script>
    </body>
    </html>
    """


# --- Owner UI ---
@app.get("/owner", response_class=HTMLResponse)
def owner_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>لوحة التحكم والتقرير الشامل للمالك</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
        <style>
            body { background-color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; }
            .btn-blue { background-color: #1d4ed8; color: #fff; border: none; font-weight: bold; border-radius: 10px; }
            .btn-blue-outline { border: 2px solid #1d4ed8; color: #1d4ed8; font-weight: bold; border-radius: 10px; background: #fff; }
            .card-custom { border-radius: 14px; border: 1px solid #e2e8f0; background: #fff; }
            .metric-label { font-size: 0.8rem; color: #64748b; font-weight: 600; display: block; }
            .metric-val { font-size: 1.25rem; font-weight: bold; margin-top: 2px; color: #1e293b; }
            .currency { font-size: 0.75rem; color: #1d4ed8; font-weight: bold; }
        </style>
    </head>
    <body class="p-3 p-md-4">
        <div class="container" style="max-width: 850px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h4 class="fw-bold text-primary mb-0">👑 لوحة المالك والرقابة والأرشيف</h4>
                <a href="/" class="btn btn-blue-outline btn-sm">اللوحة الميدانية 📱</a>
            </div>

            <div class="card card-custom p-3 mb-3">
                <div class="row g-2 align-items-center">
                    <div class="col-12 col-md-6">
                        <label class="form-label fw-bold text-secondary mb-1">📂 السجل المرجعي (اختر الدفعة للمراجعة):</label>
                        <select id="batchSelect" class="form-select fw-bold border-primary" onchange="loadOwnerData(this.value)">
                            <option value="">جاري التحميل...</option>
                        </select>
                    </div>
                    <div class="col-12 col-md-6 d-flex gap-2 pt-2 pt-md-4">
                        <button class="btn btn-blue w-100 py-2" onclick="openNewBatchModal()">➕ إضافة دفعة جديدة</button>
                        <button class="btn btn-blue w-100 py-2" onclick="recordSaleModal()">💵 تسجيل مبيعات</button>
                    </div>
                </div>
            </div>

            <!-- التقرير المالي العام -->
            <div class="card card-custom p-3 mb-3 border-start border-4 border-primary">
                <h6 class="fw-bold text-primary mb-3">💰 التقرير المالي العام للدفعة المحدد</h6>
                <div class="row text-center g-2">
                    <div class="col-4">
                        <small class="text-muted">إجمالي المصروفات</small>
                        <h5 id="o-expenses" class="fw-bold text-danger mt-1">0 <span class="currency">ج.س</span></h5>
                    </div>
                    <div class="col-4">
                        <small class="text-muted">المبيعات (الإيرادات)</small>
                        <h5 id="o-revenue" class="fw-bold text-primary mt-1">0 <span class="currency">ج.س</span></h5>
                    </div>
                    <div class="col-4">
                        <small class="text-muted">صافي الربح / الخسارة</small>
                        <h5 id="o-profit" class="fw-bold mt-1">0 <span class="currency">ج.س</span></h5>
                    </div>
                </div>
            </div>

            <!-- تفاصيل العلف المأكول حسب النوع -->
            <div class="card card-custom p-3 mb-3">
                <h6 class="fw-bold text-dark mb-3">🌾 تفاصيل استهلاك وتكلفة الأعلاف (بالأنواع)</h6>
                <div class="row g-2 text-center mb-3">
                    <div class="col-6 col-md-3">
                        <div class="p-2 border rounded bg-light">
                            <span class="metric-label">الماسكر (شوال)</span>
                            <div id="feed-masker" class="metric-val text-primary">0</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="p-2 border rounded bg-light">
                            <span class="metric-label">البادي (شوال)</span>
                            <div id="feed-badi" class="metric-val text-primary">0</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="p-2 border rounded bg-light">
                            <span class="metric-label">النامي (شوال)</span>
                            <div id="feed-nami" class="metric-val text-primary">0</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="p-2 border rounded bg-light">
                            <span class="metric-label">الناهي (شوال)</span>
                            <div id="feed-nahi" class="metric-val text-primary">0</div>
                        </div>
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center bg-light p-2 rounded border">
                    <span class="fw-bold text-secondary">إجمالي تكلفة الأعلاف للدفعة:</span>
                    <span id="o-feed-cost" class="fw-bold text-dark fs-5">0 <span class="currency">ج.س</span></span>
                </div>
            </div>

            <!-- سجل الفاكسينات واللقاحات -->
            <div class="card card-custom p-3 mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="fw-bold text-dark mb-0">💉 سجل الفاكسينات واللقاحات للدفعة</h6>
                    <span id="o-vaccine-cost" class="fw-bold text-danger">0 ج.س</span>
                </div>
                <div id="vaccines-list-container" class="small text-secondary">
                    جاري تحميل سجل اللقاحات...
                </div>
            </div>

            <!-- وقود وأدوية القطيع -->
            <div class="card card-custom p-3 mb-3">
                <h6 class="fw-bold text-dark mb-3">📊 حصر القطيع والنافق والجودة</h6>
                <div class="row g-3 text-center">
                    <div class="col-6 col-md-3">
                        <div class="p-2 border rounded bg-light">
                            <span class="metric-label">🐥 العدد الأولي</span>
                            <div id="o-initial" class="metric-val text-primary">0</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="p-2 border rounded bg-light">
                            <span class="metric-label">🐓 الحي الحالي</span>
                            <div id="o-live" class="metric-val text-success">0</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="p-2 border rounded bg-light">
                            <span class="metric-label">⚠️ النافق الكلي</span>
                            <div id="o-deaths" class="metric-val text-danger">0</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="p-2 border rounded bg-light">
                            <span class="metric-label">📉 نسبة النافق</span>
                            <div id="o-mortality" class="metric-val text-warning">0%</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="d-grid mb-4">
                <a href="/api/admin/backup-db" class="btn btn-blue-outline p-3">📥 تنزيل نسخة احتياطية من قاعدة البيانات والأرشيف (SQLite)</a>
            </div>
        </div>

        <script>
            let currentBatchId = null;

            async function loadOwnerData(batchId = null) {
                try {
                    const url = batchId ? `/api/analytics?batch_id=${batchId}` : '/api/analytics';
                    const res = await fetch(url);
                    const data = await res.json();
                    
                    currentBatchId = data.selected_batch_id;

                    const select = document.getElementById('batchSelect');
                    if (data.batches_list && data.batches_list.length > 0) {
                        select.innerHTML = data.batches_list.map(b => 
                            `<option value="${b.id}" ${b.id === currentBatchId ? 'selected' : ''}>${b.name}</option>`
                        ).join('');
                    } else {
                        select.innerHTML = `<option value="">لا توجد دفعات محفوظة حالياً</option>`;
                    }

                    document.getElementById('o-expenses').innerHTML = (data.total_expenses || 0).toLocaleString() + ' <span class="currency">ج.س</span>';
                    document.getElementById('o-revenue').innerHTML = (data.total_revenue || 0).toLocaleString() + ' <span class="currency">ج.س</span>';
                    
                    const profitElem = document.getElementById('o-profit');
                    const profitVal = data.net_profit || 0;
                    profitElem.innerHTML = profitVal.toLocaleString() + ' <span class="currency">ج.س</span>';
                    profitElem.className = profitVal >= 0 ? "fw-bold text-success mt-1" : "fw-bold text-danger mt-1";
                    
                    // العلف التفصيلي
                    document.getElementById('o-feed-cost').innerHTML = (data.feed_cost || 0).toLocaleString() + ' <span class="currency">ج.س</span>';
                    if (data.feed_breakdown) {
                        document.getElementById('feed-masker').innerText = (data.feed_breakdown['ماسكر'] || 0) + ' شوال';
                        document.getElementById('feed-badi').innerText = (data.feed_breakdown['بادي'] || 0) + ' شوال';
                        document.getElementById('feed-nami').innerText = (data.feed_breakdown['نامي'] || 0) + ' شوال';
                        document.getElementById('feed-nahi').innerText = (data.feed_breakdown['ناهي'] || 0) + ' شوال';
                    }

                    // الفاكسينات
                    document.getElementById('o-vaccine-cost').innerHTML = 'إجمالي اللقاحات: ' + (data.vaccine_cost || 0).toLocaleString() + ' ج.س';
                    const vListContainer = document.getElementById('vaccines-list-container');
                    if (data.vaccines_list && data.vaccines_list.length > 0) {
                        vListContainer.innerHTML = '<ul class="list-group list-group-flush">' + 
                            data.vaccines_list.map(v => 
                                `<li class="list-group-item d-flex justify-content-between align-items-center px-0 py-1">
                                    <span>💉 <strong>${v.name}</strong> <small class="text-muted">(${v.date})</small></span>
                                    <span class="fw-bold text-danger">${v.cost.toLocaleString()} ج.س</span>
                                </li>`
                            ).join('') + '</ul>';
                    } else {
                        vListContainer.innerHTML = '<div class="alert alert-light border py-2 text-center mb-0">لم يتم تسجيل فاكسينات لهذه الدفعة حتى الآن.</div>';
                    }

                    // حصر القطيع
                    document.getElementById('o-initial').innerText = (data.initial_birds || 0).toLocaleString();
                    document.getElementById('o-live').innerText = (data.live_birds || 0).toLocaleString();
                    document.getElementById('o-deaths').innerText = (data.total_deaths || 0).toLocaleString();
                    document.getElementById('o-mortality').innerText = data.mortality_rate || "0%";
                    
                } catch(e) { console.log("خطأ في التحميل"); }
            }

            async function openNewBatchModal() {
                const batchName = prompt("أدخل اسم أو رقم الدفعة الجديدة:");
                if (!batchName) return;
                const countInput = prompt("أدخل عدد الكتاكيت الأولي:");
                if (!countInput) return;
                const priceInput = prompt("أدخل سعر شراء الكتكوت الواحد (ج.س):");
                if (!priceInput) return;

                const res = await fetch('/api/batches', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ 
                        name: batchName.trim(), 
                        initial_count: parseInt(countInput.trim()), 
                        chick_price: parseFloat(priceInput.trim()) 
                    })
                });
                
                const resData = await res.json();
                if (res.ok && resData.status === "success") {
                    alert("✅ تم حفظ الدفعة بنجاح في الأرشيف الدائم!");
                    await loadOwnerData(resData.batch_id);
                }
            }

            async function recordSaleModal() {
                if (!currentBatchId) { alert("يرجى اختيار أو إضافة دفعة أولاً."); return; }
                const weight = prompt("وزن اللحم المباع (كجم):");
                const price = prompt("سعر الكيلو (ج.س):");
                if (weight && price) {
                    await fetch('/api/sales', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ batch_id: currentBatchId, total_weight_kg: parseFloat(weight), price_per_kg: parseFloat(price) })
                    });
                    alert("✅ تم تسجيل المبيعات بنجاح!");
                    loadOwnerData(currentBatchId);
                }
            }

            loadOwnerData();
        </script>
    </body>
    </html>
    """ 
