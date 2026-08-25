from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from core.models import Offer
from products.models import Category, Product


CATEGORIES = (
    ("العناية بالبشرة", "منتجات يومية للترطيب والتنظيف والإشراقة.", "serum.webp"),
    ("العناية بالجسم", "عناية متكاملة تمنح الجسم نعومة وترطيبًا.", "cream.webp"),
    ("العناية بالشعر", "منتجات مختارة لشعر صحي وأكثر حيوية.", "mist.webp"),
    ("الشفاه", "ترطيب وعناية ولمسات لون ناعمة.", "cream.webp"),
    ("المكياج", "أساسيات احترافية لإطلالة طبيعية وأنيقة.", "cream.webp"),
    ("العطور", "روائح مميزة تناسب مختلف الأوقات.", "mist.webp"),
)


PRODUCTS = (
    {
        "name": "سيروم الإشراقة بالهيالورونيك",
        "sku": "LUM-SKN-001",
        "category": "العناية بالبشرة",
        "image": "serum.webp",
        "short_description": "ترطيب مركز ولمعة صحية من أول استخدام.",
        "description": "سيروم خفيف يدعم ترطيب البشرة ويمنحها مظهرًا ممتلئًا ومشرقًا.",
        "price": "349.00",
        "old_price": "420.00",
        "size_label": "30 مل",
    },
    {
        "name": "كريم الترطيب المخملي",
        "sku": "LUM-SKN-002",
        "category": "العناية بالبشرة",
        "image": "cream.webp",
        "short_description": "راحة يومية وحاجز ترطيب متوازن.",
        "description": "كريم سريع الامتصاص مناسب للعناية اليومية بالبشرة الجافة والعادية.",
        "price": "285.00",
        "old_price": "330.00",
        "size_label": "50 مل",
    },
    {
        "name": "غسول الوجه اللطيف",
        "sku": "LUM-SKN-003",
        "category": "العناية بالبشرة",
        "image": "mist.webp",
        "short_description": "تنظيف يومي لطيف دون إحساس بالجفاف.",
        "description": "غسول رغوي خفيف يزيل الشوائب ويحافظ على راحة البشرة.",
        "price": "225.00",
        "old_price": "260.00",
        "size_label": "150 مل",
    },
    {
        "name": "بودي ميست نسمة الورد",
        "sku": "LUM-BDY-001",
        "category": "العناية بالجسم",
        "image": "mist.webp",
        "short_description": "رائحة هادئة تدوم بخفة طوال اليوم.",
        "description": "رذاذ عطري ناعم بنفحات الورد الدافئة ولمسة فانيليا.",
        "price": "219.00",
        "old_price": "260.00",
        "size_label": "200 مل",
    },
    {
        "name": "زيت الجسم الكهرماني",
        "sku": "LUM-BDY-002",
        "category": "العناية بالجسم",
        "image": "serum.webp",
        "short_description": "نعومة ولمعان من دون ملمس دهني.",
        "description": "مزيج زيوت خفيف يدعم مرونة البشرة ويتركها ناعمة.",
        "price": "310.00",
        "old_price": "360.00",
        "size_label": "100 مل",
    },
    {
        "name": "ماسك الشعر المغذي",
        "sku": "LUM-HAR-001",
        "category": "العناية بالشعر",
        "image": "cream.webp",
        "short_description": "تغذية أسبوعية لشعر أكثر نعومة.",
        "description": "ماسك كريمي بزبدة الشيا وزيت الأرجان للعناية بالأطراف الجافة.",
        "price": "325.00",
        "old_price": "375.00",
        "size_label": "250 مل",
    },
    {
        "name": "سيروم أطراف الشعر",
        "sku": "LUM-HAR-002",
        "category": "العناية بالشعر",
        "image": "serum.webp",
        "short_description": "لمعان وحماية خفيفة للأطراف.",
        "description": "سيروم خفيف يساعد على تحسين مظهر الأطراف وتقليل الهيشان.",
        "price": "249.00",
        "old_price": "290.00",
        "size_label": "50 مل",
    },
    {
        "name": "بلسم شفاه بالورد",
        "sku": "LUM-LIP-001",
        "category": "الشفاه",
        "image": "cream.webp",
        "short_description": "ترطيب مريح بلمسة وردية شفافة.",
        "description": "بلسم يومي غني يساعد على الحفاظ على نعومة الشفاه.",
        "price": "115.00",
        "old_price": "140.00",
        "size_label": "10 جم",
    },
    {
        "name": "عطر مسك الغروب",
        "sku": "LUM-PRF-001",
        "category": "العطور",
        "image": "mist.webp",
        "short_description": "مسك دافئ بنفحات فانيليا وخشب ناعم.",
        "description": "عطر شرقي حديث مناسب للاستخدام اليومي والمناسبات.",
        "price": "480.00",
        "old_price": "550.00",
        "size_label": "50 مل",
    },
    {
        "name": "برايمر ناعم للبشرة",
        "sku": "LUM-MKP-001",
        "category": "المكياج",
        "image": "cream.webp",
        "short_description": "قاعدة حريرية لمكياج متوازن.",
        "description": "برايمر خفيف يهيئ البشرة ويمنحها ملمسًا ناعمًا قبل المكياج.",
        "price": "265.00",
        "old_price": "310.00",
        "size_label": "30 مل",
    },
)


OFFERS = (
    {
        "title": "خصم روتين البشرة",
        "eyebrow": "إشراقة كل يوم",
        "subtitle": "منتجات للروتين اليومي بسعر أخف لفترة محدودة.",
        "skus": ("LUM-SKN-001", "LUM-SKN-002", "LUM-SKN-003"),
        "order": 1,
    },
    {
        "title": "عناية الشعر والجسم",
        "eyebrow": "وقت العناية",
        "subtitle": "مجموعة مختارة للنعومة والترطيب من الرأس إلى القدمين.",
        "skus": ("LUM-BDY-001", "LUM-BDY-002", "LUM-HAR-001", "LUM-HAR-002"),
        "order": 2,
    },
    {
        "title": "اختيارات الجمال",
        "eyebrow": "الأكثر أناقة",
        "subtitle": "لمسات مختارة من المكياج والعطور والعناية بالشفاه.",
        "skus": ("LUM-LIP-001", "LUM-PRF-001", "LUM-MKP-001"),
        "order": 3,
    },
)


class Command(BaseCommand):
    help = "إنشاء أقسام ومنتجات وعروض تجريبية فقط، دون تغيير إعدادات المتجر"

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="إنشاء البيانات دون نسخ الصور التجريبية إلى Media.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        demo_dir = settings.BASE_DIR / "static" / "images" / "demo"
        category_objects = {}
        created_categories = 0
        created_products = 0
        created_offers = 0

        for order, (name, description, image_name) in enumerate(CATEGORIES, 1):
            category, created = Category.objects.get_or_create(
                name=name,
                defaults={
                    "description": description,
                    "is_active": True,
                    "order": order,
                },
            )
            created_categories += int(created)
            if not options["no_images"]:
                self.attach_if_empty(
                    category,
                    "image",
                    demo_dir / image_name,
                    f"demo-category-{order}.webp",
                )
                category.save()
            category_objects[name] = category

        product_objects = {}
        for index, item in enumerate(PRODUCTS, 1):
            product, created = Product.objects.get_or_create(
                sku=item["sku"],
                defaults={
                    "name": item["name"],
                    "category": category_objects[item["category"]],
                    "short_description": item["short_description"],
                    "description": item["description"],
                    "price": Decimal(item["price"]),
                    "old_price": Decimal(item["old_price"]),
                    "stock_quantity": 12 + index * 2,
                    "brand": "لُمعة",
                    "country_of_origin": "مصر",
                    "size_label": item["size_label"],
                    "is_active": True,
                    "is_featured": index <= 6,
                    "is_best_seller": index in {1, 4, 6, 9},
                    "is_new": index in {2, 3, 7, 10},
                    "meta_title": item["name"],
                    "meta_description": item["short_description"],
                },
            )
            created_products += int(created)
            if not options["no_images"]:
                self.attach_if_empty(
                    product,
                    "main_image",
                    demo_dir / item["image"],
                    f"demo-product-{index}.webp",
                )
                product.save()
            product_objects[item["sku"]] = product

        for item in OFFERS:
            offer, created = Offer.objects.get_or_create(
                title=item["title"],
                defaults={
                    "eyebrow": item["eyebrow"],
                    "subtitle": item["subtitle"],
                    "button_text": "عرض التفاصيل",
                    "is_active": True,
                    "order": item["order"],
                },
            )
            created_offers += int(created)
            discounted_products = Product.objects.filter(
                pk__in=[product_objects[sku].pk for sku in item["skus"]],
                old_price__isnull=False,
                old_price__gt=F("price"),
            )
            offer.products.add(*discounted_products)

        self.stdout.write(
            self.style.SUCCESS(
                "Demo catalog is ready: "
                f"{created_categories} new categories, "
                f"{created_products} new products, "
                f"{created_offers} new offers."
            )
        )

    @staticmethod
    def attach_if_empty(instance, field_name, source, filename):
        field = getattr(instance, field_name)
        source = Path(source)
        if not field and source.is_file():
            field.save(filename, ContentFile(source.read_bytes()), save=False)
