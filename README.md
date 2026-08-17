# متجر لُمعة للعناية والجمال

متجر إلكتروني عربي RTL مبني بـ Django، خفيف وقابل للنشر على استضافة محدودة الموارد. يدعم تصفح المنتجات والبحث والتصفية، عروضًا مجدولة بمنتجات مختارة، سلة جلسات، Checkout كضيف، الدفع عند الاستلام أو تحويل InstaPay يدوي، حسابات العملاء والمفضلة، ولوحة إدارة عربية مخصصة.

الواجهة تستخدم خط `IBM Plex Sans Arabic` محليًا بأربعة أوزان، ونظام SVG محليًا مبنيًا على Lucide مع علامات الشبكات الاجتماعية من Simple Icons. لا تعتمد الخطوط أو الأيقونات على CDN؛ راجع `THIRD_PARTY_ASSETS.md` للتراخيص والمصادر.

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
- `Offer` يجمع المنتجات المخفضة داخل حملة قابلة للجدولة والترتيب والإيقاف من لوحة التحكم.

إنشاء الطلب يتم داخل معاملة SQLite قصيرة بمفتاح Idempotency. حجز المخزون يستخدم `UPDATE ... WHERE stock >= reserved + quantity` الذري بدل الاعتماد على `select_for_update` غير الفعال في SQLite. يُخصم المخزون فعليًا عند التأكيد، ويُحرر الحجز عند الإلغاء أو فشل الدفع أو انتهاء المهلة. كل الأسعار والإجماليات تعاد حسابها في الخادم.

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
- SQLite 3 هي قاعدة البيانات الوحيدة للتطوير والإنتاج.

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

ثم افتح `http://127.0.0.1:8000/` (باستخدام HTTP وليس HTTPS). يستخدم
`manage.py` إعدادات التطوير المحلية تلقائيًا، بينما تبقى إعدادات HTTPS الخاصة
بالإنتاج معزولة في إعدادات النشر.

ثم افتح `http://127.0.0.1:8000/`. أعطِ المستخدم الإداري صلاحية Staff للوصول إلى `/dashboard/`؛ المستخدم المنشأ عبر `createsuperuser` يملكها تلقائيًا.

أمر `seed_demo` آمن للتكرار ويضيف إعدادات المتجر والتصنيفات والمنتجات ومناطق الشحن والبانرات والصفحات وكوبون `WELCOME10`.

## متغيرات البيئة

انسخ `.env.example` إلى `.env` أو عرّف القيم في منصة الاستضافة. يقرأ المشروع ملف `.env` البسيط مباشرة دون مكتبة إضافية، وتبقى قيم بيئة النظام صاحبة الأولوية.

```env
DJANGO_SECRET_KEY=a-long-random-secret
DEBUG=False
ALLOWED_HOSTS=example.com,www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
SQLITE_PATH=/persistent-data/db.sqlite3
SQLITE_TIMEOUT=20
SQLITE_ENABLE_WAL=True
PRIVATE_MEDIA_ROOT=/persistent-data/private_media
```

يجب وضع ملف SQLite ومجلدي `media` و`private_media` على قرص دائم، وتشغيل نسخة تطبيق واحدة فقط. وضع WAL مناسب على قرص محلي دائم؛ لا تفعّله فوق NFS أو نظام ملفات مشترك غير موثوق.

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

## النشر على PythonAnywhere بالخطة المجانية

المشروع مجهز لمسار WSGI التقليدي في PythonAnywhere. الإعداد الخاص بالمنصة هو
`config.settings_pythonanywhere`. توضع قاعدة البيانات والنسخ الاحتياطية في مجلد مستقل بجوار مستودع Git، بينما تبقى ملفات العرض داخل مجلد المشروع:

```text
/home/YOUR_USERNAME/cosmetics_data/db.sqlite3  # قاعدة البيانات، خارج Git
/home/YOUR_USERNAME/cosmetics_data/backups/    # النسخ الاحتياطية، خارج Git
/home/YOUR_USERNAME/Cosmetics/staticfiles/     # ناتج collectstatic
/home/YOUR_USERNAME/Cosmetics/media/           # صور المنتجات العامة
/home/YOUR_USERNAME/Cosmetics/private_media/   # إيصالات الدفع الخاصة
```

لا تربط `private_media` بعنوان URL عام؛ إيصالات الدفع تُرسل من View محمي بالصلاحيات.

### 1. رفع المشروع وتجهيز البيئة

اجعل اسم مجلد المشروع `Cosmetics` داخل مجلد حسابك، سواء رفعته من تبويب Files أو نسخته من Git. من Bash Console:

```bash
cd ~/Cosmetics
bash setup_pythonanywhere.sh
```

السكريبت يستخدم Python 3.13 افتراضيًا، ينشئ البيئة
`/home/YOUR_USERNAME/.virtualenvs/cosmetics`، يولد `.env` سريًا بصلاحية `600`، وينشئ المجلدات، ثم ينفذ `migrate` و`setup_roles` و`collectstatic` وفحص الإنتاج ونسخة احتياطية.

إذا اخترت إصدار Python مختلفًا في صفحة Web، يجب أن يطابق البيئة الافتراضية، مثل:

```bash
PYTHON_BIN=/usr/local/bin/python3.12 bash setup_pythonanywhere.sh
```

إذا كانت القاعدة الحالية موجودة في `~/Cosmetics/data/db.sqlite3` أو `~/Cosmetics/db.sqlite3`، ينسخها السكريبت إلى `~/cosmetics_data/db.sqlite3` باستخدام SQLite Backup API ويتحقق من سلامتها، ولا يكتب مطلقًا فوق قاعدة خارجية موجودة. بعد نجاح النقل يستخدم المتجر المسار الخارجي فقط، ولذلك لا يؤثر `git pull` في بياناته. ارفع كذلك محتويات `media/` إن كنت تريد نقل صور المتجر الحالية.

بعد سحب هذا التحديث على متجر قائم، نفّذ سكربت الإعداد مرة واحدة **قبل Reload** كي تُنقل القاعدة الحالية ويتحدث ملف `.env` تلقائيًا:

```bash
cd ~/Cosmetics
bash setup_pythonanywhere.sh
```

في حسابك الحالي تكون البنية النهائية كالتالي:

```text
/home/Ahmedalgohary1/Cosmetics/                 # أكواد الموقع
/home/Ahmedalgohary1/cosmetics_data/db.sqlite3 # قاعدة البيانات خارج Git
```

لإنشاء كتالوج تجريبي فقط، يتضمن 6 أقسام و10 منتجات و3 عروض دون تغيير اسم المتجر أو بيانات التواصل، نفّذ:

```bash
cd ~/Cosmetics
python manage.py seed_catalog_demo --settings=config.settings_pythonanywhere
```

الأمر آمن للتكرار؛ يعتمد على أسماء الأقسام وأرقام SKU وعناوين العروض لمنع إنشاء نسخ مكررة. استخدم `--no-images` إذا أردت إنشاء السجلات دون نسخ الصور التجريبية إلى مجلد Media.

### 2. إنشاء Web app

من تبويب **Web**:

1. اختر **Add a new web app** ثم **Manual configuration** وPython 3.13.
2. ضع مسار Virtualenv:

   ```text
   /home/YOUR_USERNAME/.virtualenvs/cosmetics
   ```

3. افتح ملف WSGI الظاهر في الصفحة واستبدل محتواه بمحتوى `~/Cosmetics/pythonanywhere_wsgi.py`.
4. أضف ربطين فقط في **Static files**:

   | URL | Directory |
   | --- | --- |
   | `/static/` | `/home/YOUR_USERNAME/Cosmetics/staticfiles` |
   | `/media/` | `/home/YOUR_USERNAME/Cosmetics/media` |

5. فعّل **Force HTTPS** إن ظهر الخيار، ثم اضغط **Reload**.

اختبر ملفًا ثابتًا مباشرة من:

```text
https://YOUR_USERNAME.pythonanywhere.com/static/css/style.css
```

لا تستخدم `runserver` ولا Gunicorn داخل PythonAnywhere؛ المنصة تستدعي WSGI بنفسها. بعد كل تحديث شغّل:

```bash
cd ~/Cosmetics
source ~/.virtualenvs/cosmetics/bin/activate
pip install -r requirements.txt
python manage.py migrate --settings=config.settings_pythonanywhere
python manage.py collectstatic --noinput --settings=config.settings_pythonanywhere
python manage.py check --deploy --settings=config.settings_pythonanywhere
```

ثم Reload من تبويب Web. أنشئ المدير أول مرة فقط:

```bash
python manage.py createsuperuser --settings=config.settings_pythonanywhere
python manage.py setup_roles --settings=config.settings_pythonanywhere
```

### 3. قيود الخطة المجانية

- الخطة المجانية الحديثة توفر Web worker واحدًا و512 MiB تقريبًا؛ وهذا يطابق إعداد SQLite أحادي العامل، لكن يلزم مراقبة مساحة الصور والنسخ الاحتياطية.
- قاعدة SQLite مناسبة لمتجر صغير منخفض التزامن هنا، وليست خيارًا جيدًا لحمل مرتفع. `SQLITE_ENABLE_WAL=False` متعمد على PythonAnywhere.
- الحسابات المجانية الجديدة لا تتضمن Scheduled Tasks. لذلك يحرر التطبيق الحجوزات المنتهية تلقائيًا قبل أي Checkout جديد. نفذ الأمر اليدوي أيضًا عند الدخول للصيانة:

  ```bash
  python manage.py release_expired_reservations --settings=config.settings_pythonanywhere
  ```

- احتفظ بآخر ثلاث نسخ فقط على المساحة المجانية، ونزّل نسخة خارج المنصة بعد أي تحديث مهم:

  ```bash
  python manage.py backup_database --output-dir ~/cosmetics_data/backups --keep 3 --settings=config.settings_pythonanywhere
  ```

- التطبيق يعيد توجيه HTTP إلى HTTPS ويستخدم Cookies آمنة. يبقى HSTS لمدة ساعة مبدئيًا، ولا يُفعل Preload على نطاق PythonAnywhere المشترك.
- البريد مضبوط افتراضيًا على Console backend، فتظهر الرسائل في Error log ولا تصل للمستخدم. الاتصال بمزودي SMTP/SMS الخارجيين على الخطة المجانية يخضع لقائمة السماح لدى PythonAnywhere؛ لا تفعّل استعادة كلمة المرور بالبريد أو OTP كخدمة فعلية قبل اختبار المزود.
- يجب تمديد صلاحية Web app المجاني من لوحة PythonAnywhere دوريًا وفق سياسة الحساب.

ملف `.env.pythonanywhere.example` مرجع فقط؛ `.env` الحقيقي مولد محليًا ومستبعد من Git. لا تنشر قيمة `DJANGO_SECRET_KEY` ولا كلمة مرور البريد.

## النسخ الاحتياطي والاستعادة

ينشئ الأمر التالي نسخة SQLite متسقة أثناء التشغيل، ينفذ `integrity_check`، ويحتفظ بآخر 10 نسخ:

```bash
python manage.py backup_database --output-dir /persistent-backups --keep 10
```

جدوله يوميًا، وانسخ كذلك `media` و`private_media` إلى موقع منفصل مشفر. للاستعادة: أوقف نسخة التطبيق الوحيدة، احتفظ بنسخة من الملف الحالي، انسخ النسخة المتحققة إلى `SQLITE_PATH`، شغّل `python manage.py migrate`، ثم تحقق بـ `PRAGMA integrity_check` قبل إعادة الخدمة.

على استضافة تدعم المهام المجدولة، شغّل دوريًا:

```bash
python manage.py release_expired_reservations
```

لتحرير حجوزات المخزون والقسائم المنتهية. على حساب PythonAnywhere مجاني حديث، ينفذ Checkout التنظيف تلقائيًا ويمكن تشغيل الأمر يدويًا عند الصيانة. أنشئ الأدوار الإدارية أو حدثها بأمان عبر `python manage.py setup_roles`.

## الاختبارات

```bash
python manage.py test
```

تغطي الاختبارات نموذج المنتج، حساب السلة، الشحن، الكوبونات، إنشاء الطلب، خصم المخزون، التحقق من إثبات InstaPay، وصلاحيات لوحة الإدارة.
