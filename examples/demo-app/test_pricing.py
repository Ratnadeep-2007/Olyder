import unittest
from pricing import total


class PricingTests(unittest.TestCase):
    def test_checkout(self):
        self.assertEqual(total(50, 2), 100.0)

    def test_discount(self):
        self.assertEqual(total(100, 1, 25), 75.0)

    def test_rejects_negative_price(self):
        with self.assertRaises(ValueError):
            total(-1, 1)


if __name__ == "__main__":
    unittest.main()
