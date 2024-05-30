class Order:
    def __init__(self, db):
        self.collection = db['orders']

    def create_order(self, order_data):
        return self.collection.insert_one(order_data)

    def get_order(self, order_id):
        return self.collection.find_one({"orderId": order_id})
