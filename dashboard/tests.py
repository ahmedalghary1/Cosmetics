from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from core.models import ContentPage, Offer
from orders.models import Order, ShippingZone
from products.models import BundleItem, Category, InventoryBatch, Product


def image_upload(name="offer.jpg"):
    output = BytesIO()
    Image.new("RGB", (40, 40), "beige").save(output, "JPEG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/jpeg")


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)

    def user_for_role(self, role):
        user = get_user_model().objects.create_user(
            username=f"{role}-user", password="safe-password", is_staff=True,
        )
        user.groups.add(Group.objects.get(name=role))
        return user

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)

    def test_regular_and_unassigned_staff_cannot_access_dashboard(self):
        regular = get_user_model().objects.create_user(username="regular", password="safe-password")
        self.client.force_login(regular)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)
        staff = get_user_model().objects.create_user(username="staff", password="safe-password", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)

    def test_orders_manager_cannot_change_catalog(self):
        self.client.force_login(self.user_for_role("Orders Manager"))
        self.assertEqual(self.client.get(reverse("dashboard:orders")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:products")).status_code, 403)

    def test_catalog_manager_cannot_view_orders(self):
        self.client.force_login(self.user_for_role("Catalog Manager"))
        self.assertEqual(self.client.get(reverse("dashboard:products")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:orders")).status_code, 403)

    def test_superuser_management_pages_render(self):
        user = get_user_model().objects.create_superuser(
            username="admin", password="safe-password", email="admin@example.com",
        )
        self.client.force_login(user)
        urls = [
            "home", "products", "product_add", "inventory", "batches", "batch_add",
            "variant_options", "variant_option_add", "categories", "category_add",
            "orders", "payments", "returns", "users", "shipping", "shipping_add",
            "coupons", "coupon_add", "banners", "banner_add", "offers", "offer_add",
            "pages", "page_add", "gallery", "gallery_add", "routine", "routine_add",
            "settings", "messages",
        ]
        for name in urls:
            with self.subTest(name=name):
                response = self.client.get(reverse(f"dashboard:{name}"))
                self.assertEqual(response.status_code, 200)

    def test_admin_can_edit_about_copy_without_breaking_its_url(self):
        user = get_user_model().objects.create_superuser(
            username="content-admin", password="safe-password", email="content@example.com",
        )
        page, _ = ContentPage.objects.update_or_create(
            slug="من-نحن", defaults={"title": "من نحن", "content": "النص القديم", "is_active": True},
        )
        self.client.force_login(user)

        response = self.client.post(reverse("dashboard:page_edit", args=[page.pk]), {
            "title": "قصتنا",
            "slug": "رابط-غير-مسموح",
            "content": "نص جديد من لوحة التحكم",
            "meta_title": "قصتنا",
            "meta_description": "تعرفي علينا",
            "is_active": "on",
        })

        self.assertRedirects(response, reverse("dashboard:pages"))
        page.refresh_from_db()
        self.assertEqual(page.slug, "من-نحن")
        self.assertEqual(page.content, "نص جديد من لوحة التحكم")
        self.assertContains(self.client.get(reverse("core:about")), "نص جديد من لوحة التحكم")

    def test_order_filters_remain_selected_after_submit(self):
        user = get_user_model().objects.create_superuser(
            username="filter-admin", password="safe-password", email="filter@example.com",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:orders"), {
            "period": "month",
            "status": Order.Status.NEW,
            "payment_method": Order.PaymentMethod.INSTAPAY,
            "payment_status": Order.PaymentStatus.PENDING,
        })

        self.assertEqual(response.status_code, 200)
        for value in (
            "month", Order.Status.NEW, Order.PaymentMethod.INSTAPAY,
            Order.PaymentStatus.PENDING,
        ):
            with self.subTest(value=value):
                self.assertContains(response, f'value="{value}" selected')

    def test_catalog_manager_can_create_offer(self):
        user = self.user_for_role("Catalog Manager")
        category = Category.objects.create(name="العناية")
        product = Product.objects.create(
            name="سيروم مخفض", sku="OFFER-1", category=category, description="وصف",
            price=Decimal("80.00"), old_price=Decimal("100.00"), stock_quantity=5,
        )
        self.client.force_login(user)
        response = self.client.post(reverse("dashboard:offer_add"), {
            "eyebrow": "لفترة محدودة", "title": "عرض الأسبوع",
            "subtitle": "خصومات مختارة", "products": [product.pk],
            "button_text": "شاهدي العرض", "button_url": "",
            "starts_at": "", "ends_at": "", "is_active": "on", "order": 1,
        })
        self.assertRedirects(response, reverse("dashboard:offers"))
        self.assertTrue(Offer.objects.filter(title="عرض الأسبوع").exists())

    def test_catalog_manager_can_create_offer_as_one_purchasable_bundle(self):
        user = self.user_for_role("Catalog Manager")
        category = Category.objects.create(name="العناية الشخصية")
        first = Product.objects.create(
            name="بودي سبلاش", sku="BOX-SPRAY", category=category,
            description="وصف", price=Decimal("300"), stock_quantity=4,
        )
        second = Product.objects.create(
            name="كريم قدم", sku="BOX-CREAM", category=category,
            description="وصف", price=Decimal("200"), stock_quantity=3,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("dashboard:offer_add"), {
            "eyebrow": "بوكس كامل", "title": "بوكس العناية الشخصية",
            "subtitle": "كل منتجات العناية في بوكس واحد",
            "sell_as_bundle": "on", "image": image_upload(),
            "bundle_price": "400.00", "bundle_old_price": "500.00",
            "products": [first.pk, second.pk], "button_text": "اطلبي العرض",
            "button_url": "", "starts_at": "", "ends_at": "",
            "is_active": "on", "order": 0,
        })

        self.assertRedirects(response, reverse("dashboard:offers"))
        offer = Offer.objects.get(title="بوكس العناية الشخصية")
        bundle = offer.bundle_product
        self.assertIsNotNone(bundle)
        self.assertTrue(bundle.is_bundle)
        self.assertEqual(bundle.price, Decimal("400.00"))
        self.assertEqual(bundle.bundle_items.count(), 2)
        self.assertEqual(offer.get_url(), bundle.get_absolute_url())

        home = self.client.get(reverse("core:home"))
        self.assertContains(home, bundle.get_absolute_url())
        self.assertContains(self.client.get(bundle.get_absolute_url()), "محتويات الباقة")

        self.client.post(reverse("cart:add", args=[bundle.pk]), {"quantity": 1})
        cart = self.client.session["cart"]
        self.assertEqual(cart, {f"p:{bundle.pk}": 1})

    def test_catalog_manager_can_create_bundle_with_components(self):
        user = self.user_for_role("Catalog Manager")
        category = Category.objects.create(name="الباقات")
        component = Product.objects.create(
            name="كريم مكوّن", sku="COMPONENT-1", category=category,
            description="وصف", price=Decimal("100"), stock_quantity=5,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("dashboard:product_add"), {
            "name": "بوكس العناية", "slug": "", "sku": "BUNDLE-1",
            "category": category.pk, "short_description": "باقة كاملة",
            "description": "وصف الباقة", "price": "250.00", "old_price": "300.00",
            "stock_quantity": 0, "is_bundle": "on", "is_active": "on",
            "bundle-TOTAL_FORMS": 3, "bundle-INITIAL_FORMS": 0,
            "bundle-MIN_NUM_FORMS": 0, "bundle-MAX_NUM_FORMS": 1000,
            "bundle-0-product": component.pk, "bundle-0-variant": "",
            "bundle-0-quantity": 2,
            "bundle-1-product": "", "bundle-1-variant": "", "bundle-1-quantity": 1,
            "bundle-2-product": "", "bundle-2-variant": "", "bundle-2-quantity": 1,
        })

        self.assertRedirects(
            response,
            reverse("dashboard:products"),
            msg_prefix=(
                f"product_errors={response.context['form'].errors if response.status_code == 200 else {}} "
                f"bundle_errors={response.context['formset'].errors if response.status_code == 200 else {}} "
                f"bundle_non_form={response.context['formset'].non_form_errors() if response.status_code == 200 else {}}"
            ),
        )
        bundle = Product.objects.get(sku="BUNDLE-1")
        self.assertTrue(bundle.is_bundle)
        self.assertEqual(
            BundleItem.objects.get(bundle=bundle, product=component).quantity,
            2,
        )

    def test_unreferenced_product_can_be_deleted(self):
        user = get_user_model().objects.create_superuser(
            username="delete-admin", password="safe-password", email="delete@example.com",
        )
        category = Category.objects.create(name="منتجات قابلة للحذف")
        product = Product.objects.create(
            name="منتج مؤقت", sku="DELETE-1", category=category,
            description="وصف", price=Decimal("100.00"), stock_quantity=0,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("dashboard:product_delete", args=[product.pk]))

        self.assertRedirects(response, reverse("dashboard:products"))
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_product_with_inventory_history_is_archived_instead_of_error(self):
        user = get_user_model().objects.create_superuser(
            username="archive-admin", password="safe-password", email="archive@example.com",
        )
        category = Category.objects.create(name="منتجات لها مخزون")
        product = Product.objects.create(
            name="منتج مرتبط", sku="ARCHIVE-1", category=category,
            description="وصف", price=Decimal("100.00"), stock_quantity=2,
        )
        InventoryBatch.objects.create(
            product=product, batch_number="BATCH-1", quantity=2,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("dashboard:product_delete", args=[product.pk]), follow=True,
        )

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.assertContains(response, "تم إيقافه وإخفاؤه من المتجر")

    def test_only_superuser_can_assign_roles(self):
        target = get_user_model().objects.create_user(username="target", password="safe-password")
        support = self.user_for_role("Customer Support")
        self.client.force_login(support)
        response = self.client.post(reverse("dashboard:user_detail", args=[target.pk]), {"is_staff": "on"})
        self.assertEqual(response.status_code, 403)

    def test_csv_export_requires_matching_permission(self):
        manager = self.user_for_role("Orders Manager")
        self.client.force_login(manager)
        self.assertEqual(self.client.get(reverse("dashboard:export_csv", args=["orders"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:export_csv", args=["products"])).status_code, 403)

    def test_payment_receipt_is_served_only_through_authorized_view(self):
        zone = ShippingZone.objects.create(name="القاهرة", shipping_cost=Decimal("50"))
        order = Order.objects.create(
            order_number="ORD-PRIVATE-1", full_name="عميل", phone="01000000000",
            governorate=zone, city="القاهرة", address="عنوان",
            subtotal=Decimal("100"), shipping_cost=Decimal("50"), total=Decimal("150"),
            payment_method=Order.PaymentMethod.INSTAPAY,
            payment_status=Order.PaymentStatus.PENDING,
            payment_receipt=SimpleUploadedFile("receipt.png", b"private-receipt", content_type="image/png"),
        )
        manager = self.user_for_role("Orders Manager")
        self.client.force_login(manager)
        response = self.client.get(reverse("dashboard:payment_receipt", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("inline", response["Content-Disposition"])
        response.close()
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:payment_receipt", args=[order.pk])).status_code, 302)
        order.payment_receipt.delete(save=False)

    def test_accountant_can_verify_payment_but_cannot_transition_order(self):
        zone = ShippingZone.objects.create(name="الجيزة", shipping_cost=Decimal("40"))
        order = Order.objects.create(
            order_number="ORD-ACCOUNTANT", full_name="عميل", phone="01000000000",
            governorate=zone, city="الجيزة", address="عنوان",
            subtotal=Decimal("100"), shipping_cost=Decimal("40"), total=Decimal("140"),
            payment_method=Order.PaymentMethod.INSTAPAY,
            payment_status=Order.PaymentStatus.PENDING,
            status=Order.Status.AWAITING_PAYMENT,
        )
        self.client.force_login(self.user_for_role("Accountant"))
        response = self.client.post(reverse("dashboard:order_detail", args=[order.pk]), {
            "status": Order.Status.CONFIRMED,
            "payment_status": Order.PaymentStatus.VERIFIED,
            "payment_note": "تمت المراجعة",
        })
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.AWAITING_PAYMENT)
        self.assertEqual(order.payment_status, Order.PaymentStatus.VERIFIED)
