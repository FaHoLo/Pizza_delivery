from copy import deepcopy
import json
import os

import db_aps
import moltin_aps


DB = db_aps.get_database_connection()

GENERIC_TEMPLATE = {
    'attachment': {
        'type': 'template',
        'payload': {
            'template_type': 'generic',
            'image_aspect_ratio': 'square',
            'elements': []
        }
    }
}


def collect_menu_message(recipient_id, category_id=None):
    message_payload = deepcopy(GENERIC_TEMPLATE)
    if category_id is None:
        category_id = os.environ['FRONT_PAGE_CAT_ID']

    menu_card = collect_menu_card(recipient_id)
    product_cards = get_product_cards(category_id)
    categories_card = get_categories_card()

    # Note: facebook can take up to 10 templates in carousel of generic templates
    message_payload['attachment']['payload']['elements'].extend([
        menu_card,
        *product_cards[:8],  # TODO handle menu with more then 8 items
        categories_card,
    ])
    return message_payload


def collect_menu_card(recipient_id):
    return {
        'title': 'Меню',
        'image_url': 'https://image.freepik.com/free-vector/pizza-logo-design-template_15146-192.jpg',
        'subtitle': 'Выберите опцию:',
        'buttons': [
            {
                'type': 'postback',
                'title': 'Корзина',
                'payload': f'fb-{recipient_id}',
            },
            {
                'type': 'postback',
                'title': 'Акции',
                'payload': f'fb-{recipient_id}',
            },
            {
                'type': 'postback',
                'title': 'Сделать заказ',
                'payload': f'fb-{recipient_id}',
            },
        ]
    }


def get_product_cards(category_id):
    db_key = f'fb_menu:{category_id}'
    product_cards = DB.get(db_key).decode('UTF-8')
    product_cards = json.loads(product_cards)
    return product_cards


def get_categories_card():
    categories_card = DB.get('categories_card').decode('utf-8')
    categories_card = json.loads(categories_card)
    return categories_card


def collect_categories_card():
    categories_card = {
        'title': 'Не нашли подходящую пиццу?',
        'image_url': 'https://primepizza.ru/uploads/position/large_0c07c6fd5c4dcadddaf4a2f1a2c218760b20c396.jpg',
        'subtitle': 'Остальные пиццы можно найти в одной из категорий:',
        'buttons': []
    }
    categories = moltin_aps.get_all_categories('sort=created_at')
    for category in categories:
        if category['id'] == os.environ['FRONT_PAGE_CAT_ID']:
            continue
        categories_card['buttons'].append({
            'type': 'postback',
            'title': category['name'],
            'payload': category['id'],
        })
    return categories_card


def collect_product_cards(products):
    product_cards = []
    for product in products:
        title = '{name} | {price}'.format(
            name=product['name'],
            price=product['meta']['display_price']['with_tax']['formatted']
        )
        image_id = product['relationships']['main_image']['data']['id']
        image_url = moltin_aps.get_file_info(image_id)['link']['href']
        product_cards.append({
            'title': title,
            'image_url': image_url,
            'subtitle': product['description'],
            'buttons': [
                {
                    'type': 'postback',
                    'title': 'Добавить в корзину',
                    'payload': product['id'],
                }
            ]
        })
    return product_cards


def collect_cart_message(cart_name):
    cart_items = moltin_aps.get_cart_items(cart_name)
    cart_card = collect_cart_card(cart_name)
    message = deepcopy(GENERIC_TEMPLATE)
    if not cart_items:
        cart_card['title'] = 'Ваша корзина пуста'
        cart_card['buttons'] = [cart_card['buttons'][-1]]
        message['attachment']['payload']['elements'].append(cart_card)
    else:
        product_cards = []
        for item in cart_items:
            product_id = item['product_id']
            item_id = item['id']
            title = '{name} | {amount} шт. | {price} за шт.'.format(
                name=item['name'],
                price=item['meta']['display_price']['with_tax']['unit']['formatted'],
                amount=item['quantity']
            )
            image_url = item['image']['href']
            buttons = [
                {
                    'type': 'postback',
                    'title': 'Добавить ещё одну',
                    'payload': f'add:{product_id}',
                },
                {
                    'type': 'postback',
                    'title': 'Убрать из корзины',
                    'payload': f'remove:{item_id}',
                },
            ]
            product_cards.append({
                'title': title,
                'image_url': image_url,
                'subtitle': item['description'],
                'buttons': [*buttons]
            })
        message['attachment']['payload']['elements'].extend([
            cart_card,
            *product_cards[:9],  # TODO handle cart with more then 9 items
        ])
    return message


def collect_cart_card(cart_name):
    cart_price = moltin_aps.get_cart(cart_name)['meta']['display_price']['with_tax']['formatted']
    return {
        'title': f'Ваш заказ на сумму {cart_price}',
        'image_url': 'https://postium.ru/wp-content/uploads/2018/08/idealnaya-korzina-internet-magazina-1068x713.jpg',
        'subtitle': 'Выберите опцию:',
        'buttons': [
            {
                'type': 'postback',
                'title': 'Самовывоз',
                'payload': 'pickup',
            },
            {
                'type': 'postback',
                'title': 'Доставка',
                'payload': 'delivery',
            },
            {
                'type': 'postback',
                'title': 'К меню',
                'payload': 'menu',
            },
        ]
    }
