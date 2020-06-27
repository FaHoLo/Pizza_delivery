from copy import deepcopy
import os

import moltin_aps


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
    products = moltin_aps.get_products_by_category_id(category_id, 'sort=name')
    product_cards = collect_product_cards(products)
    categories_card = collect_categories_card()

    # Note: facebook can take up to 10 templates in carousel of generic templates
    message_payload['attachment']['payload']['elements'].extend([
        menu_card,
        product_cards[:8],
        categories_card,
    ])
    return message_payload


def collect_menu_card(recipient_id):
    menu_card = {
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
    return menu_card


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


def collect_categories_card():
    categories_card = {
        'title': 'Не нашли подходящую пиццу?',
        'image_url': 'https://primepizza.ru/uploads/position/large_0c07c6fd5c4dcadddaf4a2f1a2c218760b20c396.jpg',
        'subtitle': 'Остальные пиццы можно найти в одной из категорий:',
        'buttons': []
    }
    categories = moltin_aps.get_all_categories('sort=created_at')
    for category in categories:
        if category['name'] == 'Front page':
            continue
        categories_card['buttons'].append({
            'type': 'postback',
            'title': category['name'],
            'payload': category['id'],
        })
    return categories_card
