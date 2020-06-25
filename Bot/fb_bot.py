import os

from dotenv import load_dotenv
from flask import Flask, request
import requests

import moltin_aps


load_dotenv()
app = Flask(__name__)
FACEBOOK_TOKEN = os.environ['PAGE_ACCESS_TOKEN']


@app.route('/', methods=['GET'])
def verify():
    '''
    При верификации вебхука у Facebook он отправит запрос на этот адрес. На него нужно ответить VERIFY_TOKEN.
    '''
    if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.challenge'):
        if not request.args.get('hub.verify_token') == os.environ['VERIFY_TOKEN']:
            return 'Verification token mismatch', 403
        return request.args['hub.challenge'], 200

    return 'Hello world', 200


@app.route('/', methods=['POST'])
def webhook():
    '''
    Основной вебхук, на который будут приходить сообщения от Facebook.
    '''
    data = request.get_json()
    if data['object'] == 'page':
        for entry in data['entry']:
            for messaging_event in entry['messaging']:
                if messaging_event.get('message'):
                    sender_id = messaging_event['sender']['id']
                    # recipient_id = messaging_event['recipient']['id']
                    # message_text = messaging_event['message']['text']
                    send_menu(sender_id)
    return 'ok', 200


def send_menu(recipient_id):
    message_payload = {
        'attachment': {
            'type': 'template',
            'payload': {
                'template_type': 'generic',
                'image_aspect_ratio': 'square',
                'elements': []
            }
        }
    }

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
    message_payload['attachment']['payload']['elements'].append(menu_card)

    front_page_cat_id = os.environ['FRONT_PAGE_CAT_ID']
    products = moltin_aps.get_products_by_category_id(front_page_cat_id, 'sort=name')
    # Note: facebook can take up to 10 templates in carousel of generic templates
    for product in products[:8]:
        title = '{name} | {price}'.format(
            name=product['name'],
            price=product['meta']['display_price']['with_tax']['formatted']
        )
        image_id = product['relationships']['main_image']['data']['id']
        image_url = moltin_aps.get_file_info(image_id)['link']['href']
        message_payload['attachment']['payload']['elements'].append(
            {
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
            }
        )

    cats_template = {
        'title': 'Не нашли нужную пиццу?',
        'image_url': 'https://primepizza.ru/uploads/position/large_0c07c6fd5c4dcadddaf4a2f1a2c218760b20c396.jpg',
        'subtitle': 'Остальные пиццы можно найти в одной из категорий:',
        'buttons': []
    }
    categories = moltin_aps.get_all_categories('sort=created_at')
    for category in categories:
        if category['name'] == 'Front page':
            continue
        cats_template['buttons'].append({
            'type': 'postback',
            'title': category['name'],
            'payload': category['id'],
        })
    message_payload['attachment']['payload']['elements'].append(cats_template)

    send_message(recipient_id, message_payload)


def send_message(recipient_id, message_payload):
    params = {'access_token': FACEBOOK_TOKEN}
    headers = {'Content-Type': 'application/json'}
    request_content = {
        'recipient': {
            'id': recipient_id
        },
        'message': message_payload,
    }

    response = requests.post(
        'https://graph.facebook.com/v7.0/me/messages',
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


if __name__ == '__main__':
    app.run(debug=True)
