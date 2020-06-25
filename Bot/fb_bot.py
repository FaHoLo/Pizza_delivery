from copy import deepcopy
import os

from dotenv import load_dotenv
from flask import Flask, request
import requests

import fb_templates
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
    message_payload = deepcopy(fb_templates.GENERIC_TEMPLATE)

    menu_card = fb_templates.collect_menu_card(recipient_id)
    message_payload['attachment']['payload']['elements'].append(menu_card)

    front_page_cat_id = os.environ['FRONT_PAGE_CAT_ID']
    products = moltin_aps.get_products_by_category_id(front_page_cat_id, 'sort=name')
    product_cards = fb_templates.collect_product_cards(products)
    # Note: facebook can take up to 10 templates in carousel of generic templates
    message_payload['attachment']['payload']['elements'].extend(product_cards[:8])

    categories_card = fb_templates.collect_categories_card()
    message_payload['attachment']['payload']['elements'].append(categories_card)

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
