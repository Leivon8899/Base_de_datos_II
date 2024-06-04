from bson import ObjectId

class Order:
    def __init__(self, db):
        self.db = db

    def insert_order(self, order_info):
        self.db.orders.insert_one(order_info)

    def get_order(self, order_id):
        order = self.db.orders.find_one({"_id": ObjectId(order_id)})
        payment = self.db.payments.find_one({"order_number": order['order_number']})
        if payment:
            order.update(payment)
        return order

    def get_all_orders(self):
        return list(self.db.orders.find({}))
