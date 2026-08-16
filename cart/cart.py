from decimal import Decimal

from products.models import Product, ProductVariant


class Cart:
    SESSION_KEY = "cart"
    COUPON_KEY = "coupon_code"

    def __init__(self, request):
        self.session = request.session
        self.user = getattr(request, "user", None)
        self.data = self.session.get(self.SESSION_KEY, {})

    @staticmethod
    def _key(product, variant=None):
        return f"v:{variant.pk}" if variant else f"p:{product.pk}"

    def add(self, product, quantity=1, replace=False, variant=None):
        if product.has_variants:
            if not variant or variant.product_id != product.pk or not variant.is_active:
                raise ValueError("يرجى اختيار الحجم أو التركيبة المطلوبة أولًا.")
        elif variant:
            raise ValueError("هذا المنتج لا يحتوي على خيارات.")
        key = self._key(product, variant)
        current = int(self.data.get(key, 0))
        requested = int(quantity) if replace else current + int(quantity)
        if requested < 1:
            self.remove(product, variant)
            return 0
        available = variant.available_stock if variant else product.available_stock
        if requested > available:
            raise ValueError("الكمية المطلوبة أكبر من المتوفر حاليًا.")
        self.data[key] = requested
        self.save()
        return requested

    def remove(self, product, variant=None):
        self.data.pop(self._key(product, variant), None)
        # Compatibility with carts created before variant support.
        if not variant:
            self.data.pop(str(product.pk), None)
        self.save()

    def clear(self):
        self.session.pop(self.SESSION_KEY, None)
        self.session.pop(self.COUPON_KEY, None)
        self.session.modified = True

    def save(self):
        self.session[self.SESSION_KEY] = self.data
        self.session.modified = True

    def __iter__(self):
        product_keys = {}
        variant_keys = {}
        for key, quantity in list(self.data.items()):
            try:
                if str(key).startswith("v:"):
                    variant_keys[int(str(key)[2:])] = (key, int(quantity))
                else:
                    product_id = int(str(key)[2:]) if str(key).startswith("p:") else int(key)
                    product_keys[product_id] = (key, int(quantity))
            except (TypeError, ValueError):
                self.data.pop(key, None)

        products = {
            product.pk: product
            for product in Product.objects.active().filter(pk__in=product_keys).select_related("category")
        }
        variants = {
            variant.pk: variant
            for variant in ProductVariant.objects.filter(
                pk__in=variant_keys, is_active=True, product__is_active=True,
                product__category__is_active=True, product__has_variants=True,
            ).select_related("product", "product__category")
        }
        valid_keys = set()
        for product_id, (key, quantity) in product_keys.items():
            product = products.get(product_id)
            if not product or product.has_variants:
                continue
            valid_keys.add(key)
            yield {
                "product": product,
                "variant": None,
                "key": key,
                "quantity": quantity,
                "price": product.price,
                "total_price": product.price * quantity,
                "available_stock": product.available_stock,
            }
        for variant_id, (key, quantity) in variant_keys.items():
            variant = variants.get(variant_id)
            if not variant:
                continue
            valid_keys.add(key)
            yield {
                "product": variant.product,
                "variant": variant,
                "key": key,
                "quantity": quantity,
                "price": variant.effective_price,
                "total_price": variant.effective_price * quantity,
                "available_stock": variant.available_stock,
            }
        missing = set(self.data) - valid_keys
        if missing:
            for key in missing:
                self.data.pop(key, None)
            self.save()

    def __len__(self):
        return sum(int(quantity) for quantity in self.data.values())

    @property
    def subtotal(self):
        return sum((item["total_price"] for item in self), Decimal("0.00"))

    @property
    def coupon(self):
        from orders.models import Coupon, CouponRedemption
        from orders.services import coupon_eligible_subtotal

        code = self.session.get(self.COUPON_KEY)
        if not code:
            return None
        try:
            coupon = Coupon.objects.get(code__iexact=code)
        except Coupon.DoesNotExist:
            return None
        items = list(self)
        eligible_subtotal = coupon_eligible_subtotal(coupon, items)
        if not coupon.is_valid_for(eligible_subtotal):
            return None
        active = [CouponRedemption.Status.RESERVED, CouponRedemption.Status.CONSUMED]
        if coupon.usage_limit is not None and coupon.redemptions.filter(status__in=active).count() >= coupon.usage_limit:
            return None
        if self.user and self.user.is_authenticated and coupon.max_uses_per_customer is not None:
            key = f"user:{self.user.pk}"
            if coupon.redemptions.filter(customer_key=key, status__in=active).count() >= coupon.max_uses_per_customer:
                return None
        return coupon

    @property
    def discount(self):
        from orders.services import coupon_eligible_subtotal

        coupon = self.coupon
        if not coupon:
            return Decimal("0.00")
        return coupon.calculate_discount(coupon_eligible_subtotal(coupon, list(self)))

    @property
    def total_after_discount(self):
        return max(self.subtotal - self.discount, Decimal("0.00"))
