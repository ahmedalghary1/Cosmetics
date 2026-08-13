# متجر لُمعة للعناية والجمال

متجر إلكتروني عربي RTL مبني بـ Django، خفيف وقابل للنشر على استضافة محدودة الموارد. يدعم تصفح المنتجات والبحث والتصفية، سلة جلسات، Checkout كضيف، الدفع عند الاستلام أو تحويل InstaPay يدوي، حسابات العملاء والمفضلة، ولوحة إدارة عربية مخصصة.

## المعمارية

المشروع Monolith منظم؛ لا يحتاج Redis أو Celery أو Docker أو إطار JavaScript للواجهة:

```text
Cosmetics/
├── config/       # الإعدادات والمسارات وWSGI/ASGI
├── core/         # إعدادات المتجر، البانرات، الصفحات، التواصل والبيانات التجريبية
├── products/     # التصنيفات والمنتجات والصور والبحث والتصفية
├── cart/         # سلة Session وحساباتها
├── orders/       # الشحن والكوبونات والطلب والدفع وخدمات المخزون
├── accounts/     # التسجيل والحساب والمفضلة
├── dashboard/    # لوحة الإدارة العربية المخصصة
├── templates/    # قوالب Django ومكوناتها المشتركة
├── static/       # ملف CSS وملف JavaScript وأصول WebP
├── media/        # الصور المرفوعة في بيئة التطوير
└── manage.py
```

العلاقات الأساسية:

- `Category` ← `Product` ← `ProductImage`.
- `Order` ← `OrderItem`، ويحفظ العنصر لقطة الاسم وSKU والسعر وقت الشراء.
- `ShippingZone` و`Coupon` يرتبطان بالطلب.
- `User` يرتبط اختياريًا بالطلبات، ويرتبط بـ `WishlistItem` و`Profile`.
- `StoreSettings` سجل وحيد يتحكم في العلامة والعملة وبيانات InstaPay والتواصل.

إنشاء الطلب يتم داخل معاملة قاعدة بيانات واحدة. تُقفل صفوف المنتجات قبل فحص الكمية وخصم المخزون للحد من السباقات، ولا تُقبل أي أسعار أو إجماليات من JavaScript. عند إلغاء الطلب تعاد الكميات مرة واحدة فقط.

## المسارات المهمة

- `/` الصفحة الرئيسية.
- `/products/` المتجر والبحث والتصفية والترتيب.
- `/category/<slug>/` صفحة التصنيف.
- `/products/<slug>/` تفاصيل المنتج.
- `/cart/` السلة.
- `/checkout/` إتمام الطلب.
- `/account/` حساب العميل وطلباته ومفضلته.
- `/dashboard/` لوحة الإدارة، لمستخدمي Staff فقط.
- `/developer-admin/` Django Admin كواجهة احتياطية للمطور.

## المتطلبات

- Python 3.11 أو أحدث.
- SQLite للتطوير. يمكن استخدام PostgreSQL عبر `DATABASE_URL` دون تعديل الكود.

## التشغيل محليًا

أنشئ البيئة الافتراضية:

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

ثبّت وشغّل:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver
```

ثم افتح `http://127.0.0.1:8000/`. أعطِ المستخدم الإداري صلاحية Staff للوصول إلى `/dashboard/`؛ المستخدم المنشأ عبر `createsuperuser` يملكها تلقائيًا.

أمر `seed_demo` آمن للتكرار ويضيف إعدادات المتجر والتصنيفات والمنتجات ومناطق الشحن والبانرات والصفحات وكوبون `WELCOME10`.

## متغيرات البيئة

انسخ `.env.example` إلى `.env` أو عرّف القيم في منصة الاستضافة. يقرأ المشروع ملف `.env` البسيط مباشرة دون مكتبة إضافية، وتبقى قيم بيئة النظام صاحبة الأولوية.

```env
SECRET_KEY=a-long-random-secret
DEBUG=False
ALLOWED_HOSTS=example.com,www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
DATABASE_URL=postgresql://user:password@host:5432/database
```

عند عدم وجود `DATABASE_URL` يستخدم المشروع `db.sqlite3`. في PostgreSQL يُفضّل إبقاء `DB_SSLMODE=require` إذا كانت الخدمة تفرض TLS.

## الملفات الثابتة والصور

- نفّذ `python manage.py collectstatic --noinput` قبل النشر.
- WhiteNoise يقدم ملفات Static مضغوطة في الإنتاج.
- الصور المرفوعة تحفظ في `MEDIA_ROOT` محليًا. يمكن تغيير `DEFAULT_FILE_STORAGE` إلى Backend تخزين خارجي لاحقًا.
- لوحة التحكم تصغّر صور الكتالوج الكبيرة وتحولها إلى WebP عند الرفع.
- إثبات تحويل InstaPay لا يعالج بصريًا حتى يظل المستند كما رفعه العميل، لكنه يخضع للتحقق من النوع والحجم والصورة الفعلية.

## إعداد الإنتاج

استخدم وحدة الإعدادات الإنتاجية أو الإعدادات الافتراضية مع `DEBUG=False`:

```bash
python manage.py check --deploy --settings=config.settings_production
python manage.py collectstatic --noinput --settings=config.settings_production
```

نقطة WSGI هي `config.wsgi:application`. يجب على منصة الاستضافة توفير مجلد Media دائم أو خدمة تخزين خارجية؛ WhiteNoise مخصص للـ Static وليس لصور العملاء.

أمر تشغيل شائع على خوادم Linux:

```bash
gunicorn config.wsgi:application
```

قبل إطلاق المتجر:

1. غيّر `SECRET_KEY` ولا تحفظه في المستودع.
2. اضبط `ALLOWED_HOSTS` و`CSRF_TRUSTED_ORIGINS`.
3. حدّث اسم المتجر وبيانات InstaPay والهاتف والسياسات من لوحة التحكم.
4. اختبر رفع ملفات Media على الاستضافة.
5. أنشئ نسخة احتياطية دورية من قاعدة البيانات وMedia.

يمكن تفعيل `SECURE_HSTS_PRELOAD=True` بعد التأكد أن النطاق وكل نطاقاته الفرعية ستعمل عبر HTTPS دائمًا؛ التفعيل المبكر قد يصعب التراجع عنه.

## الاختبارات

```bash
python manage.py test
```

تغطي الاختبارات نموذج المنتج، حساب السلة، الشحن، الكوبونات، إنشاء الطلب، خصم المخزون، التحقق من إثبات InstaPay، وصلاحيات لوحة الإدارة.
