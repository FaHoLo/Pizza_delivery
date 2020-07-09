import json

import db_aps
import fb_templates
import moltin_aps


DB = db_aps.get_database_connection()


def update_cached_cards():
    update_menu_cards()
    update_category_card()


def update_menu_cards():
    categories = moltin_aps.get_all_categories()
    for category in categories:
        products = moltin_aps.get_products_by_category_id(category['id'], 'sort=name')
        product_cards = fb_templates.collect_product_cards(products)
        product_cards = json.dumps(product_cards)
        db_key = 'fb_menu:{}'.format(category['id'])
        DB.set(db_key, product_cards)


def update_category_card():
    categories_card = fb_templates.collect_categories_card()
    categories_card = json.dumps(categories_card)
    DB.set('categories_card', categories_card)
