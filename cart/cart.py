from decimal import Decimal

from products.models import Product


class Cart:
    SESSION_KEY = "cart"
    COUPON_KEY = "coupon_code"

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(self.SESSION_KEY, {})

    def add(self, product, quantity=1, replace=False):
        product_id = str(product.pk)
        current = int(self.data.get(product_id, 0))
        requested = int(quantity) if replace else current + int(quantity)
        if requested < 1:
            self.remove(product)
            return 0
        if requested > product.stock_quantity:
            raise ValueError("الكمية المطلوبة أكبر من المتوفر حاليًا.")
        self.data[product_id] = requested
        self.save()
        return requested

    def remove(self, product):
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
        product_ids = self.data.keys()
        products = Product.objects.filter(pk__in=product_ids, is_active=True).select_related("category")
        found = set()
        for product in products:
            found.add(str(product.pk))
            quantity = int(self.data[str(product.pk)])
            yield {
                "product": product,
                "quantity": quantity,
                "price": product.price,
                "total_price": product.price * quantity,
            }
        missing = set(product_ids) - found
        if missing:
            for product_id in missing:
                self.data.pop(product_id, None)
            self.save()

    def __len__(self):
        return sum(int(quantity) for quantity in self.data.values())

    @property
    def subtotal(self):
        return sum((item["total_price"] for item in self), Decimal("0.00"))

    @property
    def coupon(self):
        from orders.models import Coupon

        code = self.session.get(self.COUPON_KEY)
        if not code:
            return None
        try:
            coupon = Coupon.objects.get(code__iexact=code)
        except Coupon.DoesNotExist:
            return None
        return coupon if coupon.is_valid_for(self.subtotal) else None

    @property
    def discount(self):
        coupon = self.coupon
        return coupon.calculate_discount(self.subtotal) if coupon else Decimal("0.00")

    @property
    def total_after_discount(self):
        return max(self.subtotal - self.discount, Decimal("0.00"))
