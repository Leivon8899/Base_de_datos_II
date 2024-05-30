class Product:
    def __init__(self, db):
        self.collection = db['products']

    def create_product(self, product_data):
        return self.collection.insert_one(product_data)

    def get_product(self, product_id):
        return self.collection.find_one({"productId": product_id})

    def update_product(self, product_id, update_data):
        return self.collection.update_one({"productId": product_id}, {"$set": update_data})

    def delete_product(self, product_id):
        return self.collection.delete_one({"productId": product_id})

    def get_all_products(self):
        return list(self.collection.find({}))
