from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Banner, ContentPage, Offer, RoutineStep, SocialGalleryImage, StoreSettings
from orders.models import Coupon, ShippingZone
from products.models import Category, Product


class Command(BaseCommand):
    help = "إنشاء بيانات عرض عربية للمتجر"

    def handle(self, *args, **options):
        demo_dir = settings.BASE_DIR / "static" / "images" / "demo"
        store = StoreSettings.load()
        store.store_name = "لُمعة"
        store.phone = "01000000000"
        store.whatsapp = "201000000000"
        store.email = "hello@example.com"
        store.address = "القاهرة، مصر"
        store.currency = "ج.م"
        store.free_shipping_threshold = Decimal("1200.00")
        store.header_announcement = "شحن مجاني للطلبات التي تزيد عن 1200 ج.م"
        store.instapay_account_name = "متجر لُمعة"
        store.instapay_address = "instapay@example"
        store.whatsapp_enabled = True
        store.save()

        category_data = [
            ("العناية بالبشرة", "منتجات تمنح بشرتك الترطيب والإشراقة.", "serum.webp"),
            ("العناية بالجسم", "عناية يومية ناعمة من الرأس إلى القدمين.", "cream.webp"),
            ("العناية بالشعر", "روتين متوازن لشعر أكثر حيوية.", "mist.webp"),
            ("الشفاه", "ترطيب ولمسات لون رقيقة.", "mist.webp"),
            ("المكياج", "أساسيات خفيفة لجمالك الطبيعي.", "cream.webp"),
            ("الأظافر", "ألوان وعناية لتفاصيل أنيقة.", "mist.webp"),
            ("العطور", "روائح دافئة تترك أثرًا.", "serum.webp"),
            ("الرموش والحواجب", "تفاصيل تبرز جمال عينيك.", "serum.webp"),
        ]
        categories = {}
        for order, (name, description, image_name) in enumerate(category_data, 1):
            category, _ = Category.objects.get_or_create(name=name, defaults={"description": description, "order": order})
            category.description = description
            category.order = order
            category.is_active = True
            self.attach_if_empty(category, "image", demo_dir / image_name, f"category-{order}.webp")
            category.save()
            categories[name] = category

        product_data = [
            ("سيروم الإشراقة بالهيالورونيك", "LUM-SKN-001", "العناية بالبشرة", "serum.webp", "ترطيب مركز ولمعة صحية من أول استخدام.", "سيروم خفيف يدعم ترطيب البشرة ويمنحها مظهرًا ممتلئًا ومشرقًا.", "حمض الهيالورونيك، بانثينول، جلسرين", "ضعي 2-3 قطرات على بشرة نظيفة.", "349", "420", True, True),
            ("كريم الترطيب المخملي", "LUM-SKN-002", "العناية بالبشرة", "cream.webp", "راحة يومية وحاجز ترطيب متوازن.", "كريم غني سريع الامتصاص للعناية بالبشرة الجافة والعادية.", "سيراميد، سكوالان، زبدة الشيا", "استخدميه صباحًا ومساءً.", "285", None, True, False),
            ("بودي ميست نسمة الورد", "LUM-BDY-001", "العناية بالجسم", "mist.webp", "رائحة هادئة تدوم بخفة طوال اليوم.", "رذاذ عطري ناعم بنفحات ورد دافئة ولمسة فانيليا.", "ماء عطري، جلسرين نباتي", "رشيه على الجسم من مسافة 15 سم.", "219", "260", True, True),
            ("زيت الجسم الكهرماني", "LUM-BDY-002", "العناية بالجسم", "serum.webp", "نعومة ولمعان من دون ملمس دهني.", "مزيج زيوت خفيف يدعم مرونة البشرة ويتركها ناعمة.", "زيت اللوز، الجوجوبا، فيتامين هـ", "دلّكي كمية قليلة بعد الاستحمام.", "310", None, False, True),
            ("ماسك الشعر المغذي", "LUM-HAR-001", "العناية بالشعر", "cream.webp", "تغذية أسبوعية لشعر أكثر نعومة.", "ماسك كريمي يعيد الحيوية للأطراف الجافة.", "زبدة الشيا، زيت الأرجان", "يترك 10 دقائق ثم يشطف.", "325", "375", True, False),
            ("بلسم شفاه بالورد", "LUM-LIP-001", "الشفاه", "cream.webp", "ترطيب مريح بلمسة وردية شفافة.", "بلسم يومي غني يحافظ على نعومة الشفاه.", "زبدة الكاكاو، شمع نباتي", "يستخدم عند الحاجة.", "115", None, True, True),
            ("زيت الرموش والحواجب", "LUM-EYE-001", "الرموش والحواجب", "serum.webp", "خطوة ليلية بسيطة لمظهر أكثر كثافة.", "تركيبة زيوت مختارة للعناية بالرموش والحواجب.", "زيت الخروع، فيتامين هـ", "يوضع مساءً بكمية قليلة.", "195", "230", False, True),
            ("عطر مسك الغروب", "LUM-PRF-001", "العطور", "mist.webp", "مسك دافئ بنفحات فانيليا وخشب ناعم.", "عطر شرقي حديث مناسب لكل يوم.", "كحول عطري، مزيج عطري", "يرش على نقاط النبض.", "480", "550", True, False),
            ("زيت أظافر مغذٍ", "LUM-NAL-001", "الأظافر", "serum.webp", "عناية لطيفة للجلد المحيط بالأظافر.", "زيت خفيف يساعد على الحفاظ على مظهر صحي ومرتب.", "زيت اللوز، جوجوبا", "تدلك قطرة على كل ظفر.", "145", None, False, True),
            ("برايمر ناعم للبشرة", "LUM-MKP-001", "المكياج", "cream.webp", "قاعدة حريرية لمكياج متوازن.", "برايمر خفيف يهيئ البشرة ويمنحها ملمسًا ناعمًا.", "سكوالان، سيليكا", "توزع كمية صغيرة قبل المكياج.", "265", "310", True, False),
        ]
        products = []
        for index, data in enumerate(product_data, 1):
            name, sku, category_name, image_name, short, description, ingredients, usage, price, old, best, new = data
            product = Product.objects.filter(sku=sku).first() or Product(
                sku=sku,
                name=name,
                category=categories[category_name],
                description=description,
                price=Decimal(price),
            )
            product.name = name
            product.category = categories[category_name]
            product.short_description = short
            product.description = description
            product.ingredients = ingredients
            product.usage = usage
            product.price = Decimal(price)
            product.old_price = Decimal(old) if old else None
            product.stock_quantity = 8 + index * 2
            product.is_active = True
            product.is_featured = index <= 5
            product.is_best_seller = best
            product.is_new = new
            product.meta_title = name
            product.meta_description = short
            self.attach_if_empty(product, "main_image", demo_dir / image_name, f"product-{index}.webp")
            product.save()
            products.append(product)

        zones = [("القاهرة", 60), ("الجيزة", 60), ("الإسكندرية", 75), ("القليوبية", 65), ("الدقهلية", 75), ("الغربية", 75), ("الشرقية", 75), ("الصعيد والبحر الأحمر", 95)]
        for order, (name, cost) in enumerate(zones, 1):
            ShippingZone.objects.update_or_create(name=name, defaults={"shipping_cost": cost, "is_active": True, "order": order})

        now = timezone.now()
        Coupon.objects.update_or_create(code="WELCOME10", defaults={
            "discount_type": Coupon.DiscountType.PERCENTAGE,
            "value": 10,
            "minimum_order": 300,
            "start_date": now - timedelta(days=1),
            "end_date": now + timedelta(days=365),
            "usage_limit": 500,
            "is_active": True,
        })

        hero, _ = Banner.objects.get_or_create(position=Banner.Position.HERO, order=1, defaults={"title": "جمالكِ... يبدأ من عنايتكِ"})
        hero.title = "جمالكِ... يبدأ من عنايتكِ"
        hero.subtitle = "منتجات مختارة بعناية لتمنح بشرتك طقوسًا هادئة ونتائج تحبينها."
        hero.button_text = "تسوقي المجموعة"
        hero.button_url = "/products/"
        hero.is_active = True
        self.attach_if_empty(hero, "image", demo_dir / "hero.webp", "hero.webp")
        hero.save()
        promo, _ = Banner.objects.get_or_create(position=Banner.Position.PROMO, order=1, defaults={"title": "لمسة عناية، تغيّر يومك"})
        promo.title = "لمسة عناية، تغيّر يومك"
        promo.subtitle = "روتين بسيط بتركيبات مختارة يمنح بشرتك إشراقة تشعرين بها."
        promo.button_text = "اكتشفي الآن"
        promo.button_url = "/products/?new=1"
        promo.is_active = True
        self.attach_if_empty(promo, "image", demo_dir / "ritual-banner.webp", "ritual-banner.webp")
        promo.save()

        offer, _ = Offer.objects.get_or_create(
            title="عروض لا تفوتك",
            defaults={
                "eyebrow": "وقت التدليل",
                "subtitle": "منتجات مختارة بأسعار أخف لفترة محدودة.",
                "button_text": "كل العروض",
                "is_active": True,
                "order": 1,
            },
        )
        offer.eyebrow = "وقت التدليل"
        offer.subtitle = "منتجات مختارة بأسعار أخف لفترة محدودة."
        offer.button_text = "كل العروض"
        offer.is_active = True
        offer.order = 1
        offer.save()
        offer.products.set(product for product in products if product.old_price)

        page_data = {
            "من-نحن": ("من نحن", "لُمعة متجر عناية مصري يختار منتجاته لتكون طقوس الجمال اليومية أبسط وأكثر هدوءًا. نؤمن أن العناية الحقيقية تبدأ بالاختيار الواعي والتجربة السهلة."),
            "الشحن-والتوصيل": ("الشحن والتوصيل", "نوصل إلى جميع محافظات مصر. تظهر تكلفة الشحن بوضوح فور اختيار المحافظة أثناء إتمام الطلب، ويستغرق التوصيل عادة من 2 إلى 5 أيام عمل."),
            "الاستبدال-والاسترجاع": ("الاستبدال والاسترجاع", "يمكن طلب الاستبدال أو الاسترجاع خلال 14 يومًا للمنتجات غير المفتوحة وبحالـتها الأصلية، وفق الضوابط الصحية لمنتجات العناية الشخصية."),
            "الأسئلة-الشائعة": ("الأسئلة الشائعة", "هل يمكن الدفع عند الاستلام؟ نعم.\n\nهل يتوفر InstaPay؟ نعم، يتم رفع صورة التحويل ثم مراجعتها يدويًا.\n\nكيف أعرف تكلفة الشحن؟ اختاري محافظتك في صفحة إتمام الطلب."),
            "سياسة-الخصوصية": ("سياسة الخصوصية", "نستخدم بياناتك فقط لتنفيذ طلبك وتحسين تجربتك، ولا نبيع بيانات العملاء لأي جهة. نحافظ على البيانات وفق الممارسات الأمنية المناسبة."),
            "الشروط-والأحكام": ("الشروط والأحكام", "باستخدام المتجر توافقين على تقديم بيانات صحيحة عند الطلب، وعلى سياسات الشحن والاستبدال الموضحة. الأسعار والمخزون يخضعان للتحديث."),
        }
        for slug, (title, content) in page_data.items():
            ContentPage.objects.update_or_create(slug=slug, defaults={"title": title, "content": content, "is_active": True, "meta_title": title})

        for index, (title, description, category_name, product_index) in enumerate([
            ("التنظيف", "بداية لطيفة لبشرة صافية", "العناية بالبشرة", 0),
            ("السيروم", "تركيز يناسب احتياج بشرتك", "العناية بالبشرة", 0),
            ("الترطيب", "احبسي الترطيب طوال اليوم", "العناية بالبشرة", 1),
            ("عناية الجسم", "اختتمي روتينك بنعومة", "العناية بالجسم", 2),
        ], 1):
            step, _ = RoutineStep.objects.update_or_create(order=index, defaults={
                "title": title, "description": description, "category": categories[category_name],
                "product": products[product_index], "is_active": True,
            })
            self.attach_if_empty(step, "image", demo_dir / ["cream.webp", "serum.webp", "cream.webp", "mist.webp"][index - 1], f"routine-{index}.webp")
            step.save()

        for index, image_name in enumerate(["serum.webp", "cream.webp", "mist.webp", "serum.webp", "cream.webp", "mist.webp"], 1):
            gallery, _ = SocialGalleryImage.objects.get_or_create(order=index, defaults={"alt_text": f"لحظة عناية {index}"})
            gallery.alt_text = f"لحظة عناية {index}"
            gallery.is_active = True
            self.attach_if_empty(gallery, "image", demo_dir / image_name, f"gallery-{index}.webp")
            gallery.save()

        self.stdout.write(self.style.SUCCESS("Demo data created successfully."))

    @staticmethod
    def attach_if_empty(instance, field_name, source, filename):
        field = getattr(instance, field_name)
        if not field and Path(source).exists():
            field.save(filename, ContentFile(Path(source).read_bytes()), save=False)
