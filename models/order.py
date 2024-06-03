class Order:
    def __init__(self, db):
        self.db = db

    def insert_order(self, order_info):
        self.db.orders.insert_one(order_info)
