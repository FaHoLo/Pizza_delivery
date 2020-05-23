from asyncio import sleep
import logging
import os
from textwrap import dedent

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

import db_aps
import log_config
import moltin_aps
import utils


tg_logger = logging.getLogger('tg_logger')

load_dotenv()
bot = Bot(token=os.environ['TG_BOT_TOKEN'])
delivery_bot = Bot(os.environ['TG_DELIVERY_BOT_TOKEN'])
dp = Dispatcher(bot)

CART_BUTTON = InlineKeyboardButton('Корзина', callback_data='cart')
MENU_BUTTON = InlineKeyboardButton('Меню', callback_data='menu')


def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[log_config.SendToTelegramHandler()],
        # level='DEBUG'
    )
    executor.start_polling(dp)


@dp.errors_handler()
async def handle_errors(update, exception):
    tg_logger.exception('')
    return True


@dp.callback_query_handler(lambda callback_query: True)
async def handle_callback_query(callback_query: types.CallbackQuery):
    await handle_user_reply(callback_query)


@dp.pre_checkout_query_handler(lambda query: True)
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    error_message = 'Технические неполадки на сервере оплаты :-( Попробуйте через пару минут'
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True, error_message=error_message)


@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: types.Message):
    total_amount = message.successful_payment.total_amount // 100
    currency = message.successful_payment.currency
    text = f'Заказ на сумму *{total_amount} {currency}* оплачен'
    # TODO save payment status to moltin
    await bot.send_message(message.chat.id, text, parse_mode=types.ParseMode.MARKDOWN_V2)


@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_message(update):
    await handle_user_reply(update)


async def handle_user_reply(update):
    db = db_aps.get_database_connection()
    chat_id, user_reply = handle_update(update)
    user_state = get_user_state(chat_id, user_reply, db)
    states_functions = {
        'START': handle_start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'WAITING_ADDRESS': handle_address,
        'WAITING_DELIVERY_CHOOSE': handle_delivery_choose,
        'WAITING_PAYMENT': handle_payment,
    }

    state_handler = states_functions[user_state]
    next_state = await state_handler(update)
    db.set(chat_id, next_state)
    tg_logger.debug(f'User «{chat_id}» state changed to {next_state}')


def handle_update(update):
    if type(update) == types.Message:
        chat_id = f'tg-{update.chat.id}'
        user_reply = update.text
    elif type(update) == types.CallbackQuery:
        chat_id = f'tg-{update.message.chat.id}'
        user_reply = update.data
    return chat_id, user_reply


def get_user_state(chat_id, user_reply, db):
    if user_reply == '/start':
        user_state = 'START'
    elif user_reply == '/cancel':
        user_state = 'START'
        moltin_aps.delete_cart(chat_id)
    else:
        user_state = db.get(chat_id).decode('utf-8')
    return user_state


async def handle_start(message: types.Message):
    await send_menu(message, 0)
    return 'HANDLE_MENU'


async def send_menu(message: types.Message, page_number):
    keyboard = await collect_menu_keyboard(page_number)
    await message.answer('Выберите товар:', reply_markup=keyboard)
    tg_logger.debug(f'Menu was sent to {message.chat.id}')


async def collect_menu_keyboard(page_number):
    prod_on_page = 8
    first_product_num = page_number * prod_on_page
    last_product_num = first_product_num + prod_on_page
    products = moltin_aps.get_all_products()

    keyboard = InlineKeyboardMarkup(row_width=2)
    for product in products[first_product_num:last_product_num]:
        keyboard.insert(InlineKeyboardButton(product['name'], callback_data=product['id']))

    if page_number != 0:
        keyboard.add(InlineKeyboardButton('← Пред. стр.', callback_data=f'pagination,{page_number-1}'))
    if last_product_num < len(products) and page_number != 0:
        keyboard.insert(InlineKeyboardButton('След. стр. →', callback_data=f'pagination,{page_number+1}'))
    if last_product_num < len(products) and page_number == 0:
        keyboard.add(InlineKeyboardButton('След. стр. →', callback_data=f'pagination,{page_number+1}'))
    keyboard.add(CART_BUTTON)
    tg_logger.debug('Menu keyboard was collected')
    return keyboard


async def handle_menu(callback_query: types.CallbackQuery):
    if callback_query.data == 'cart':
        await send_cart(callback_query)
        await delete_bot_message(callback_query)
        return 'HANDLE_CART'

    if 'pagination' in callback_query.data:
        page_number = int(callback_query.data.split(',')[1])
        await send_menu(callback_query.message, page_number)
        await delete_bot_message(callback_query)
        return 'HANDLE_MENU'

    product_info = moltin_aps.get_product_info(callback_query.data)
    image_id = product_info['relationships']['main_image']['data']['id']
    image_url = moltin_aps.get_file_info(image_id)['link']['href']
    product_name = product_info['name']
    text = dedent(f'''\
    {product_name}\n
    {product_info['price'][0]['amount']} {product_info['price'][0]['currency']}\n
    {product_info['description']}
    ''')
    keyboard = await collect_product_description_keyboard(callback_query.data)

    await callback_query.answer(text=product_name)
    await bot.send_photo(callback_query.message.chat.id, image_url, caption=text, reply_markup=keyboard)
    await delete_bot_message(callback_query)
    return 'HANDLE_DESCRIPTION'
    tg_logger.debug(f'{product_name} description was sent')


async def send_cart(callback_query):
    keyboard = InlineKeyboardMarkup(row_width=2).add(MENU_BUTTON)
    cart_name = f'tg-{callback_query.message.chat.id}'
    chat_id = callback_query.message.chat.id
    cart_items = moltin_aps.get_cart_items(cart_name)
    if not cart_items:
        text = 'Ваша корзина пуста.'
        tg_logger.debug(f'Got empty cart for {chat_id}')
    else:
        keyboard.insert(InlineKeyboardButton('Оплата', callback_data='pay'))
        text, keyboard = await collect_full_cart(cart_items, cart_name, keyboard)
    await callback_query.answer('Корзина')
    await bot.send_message(chat_id, text, reply_markup=keyboard)
    tg_logger.debug(f'Cart was sent to {chat_id}')


async def collect_full_cart(cart_items, cart_name, keyboard):
    text = 'Товары в вашей корзине:\n\n'
    total_price = moltin_aps.get_cart(cart_name)['meta']['display_price']['with_tax']['formatted']
    for item in cart_items:
        product_name = item['name']
        item_id = item['id']
        text += dedent(f'''\
            {product_name}
            {item['description']}
            {item['meta']['display_price']['with_tax']['unit']['formatted']} за шт.
            {item['quantity']} шт. в корзине на {item['meta']['display_price']['with_tax']['value']['formatted']}\n
        ''')
        keyboard.add(InlineKeyboardButton(f'Убрать {product_name}', callback_data=item_id))
    text += f'Всего: {total_price}'
    tg_logger.debug('Cart was collected')
    return text, keyboard


async def delete_bot_message(update):
    if type(update) == types.Message:
        await bot.delete_message(update.chat.id, update.message_id)
    elif type(update) == types.CallbackQuery:
        await bot.delete_message(update.message.chat.id, update.message.message_id)
    tg_logger.debug('Previous bot message was deleted')


async def collect_product_description_keyboard(product_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton('Добавить в корзину', callback_data=f'{product_id},1'),
    )
    keyboard.add(MENU_BUTTON)
    keyboard.insert(CART_BUTTON)
    tg_logger.debug('Description keyboard was collected')
    return keyboard


async def handle_description(callback_query: types.CallbackQuery):
    if callback_query.data == 'menu':
        await send_menu(callback_query.message, 0)
        await delete_bot_message(callback_query)
        return 'HANDLE_MENU'
    elif callback_query.data == 'cart':
        await send_cart(callback_query)
        await delete_bot_message(callback_query)
        return 'HANDLE_CART'
    else:
        product_id, number_of_kilos = callback_query.data.split(',')
        moltin_aps.add_product_to_cart(f'tg-{callback_query.message.chat.id}', product_id, int(number_of_kilos))
        await callback_query.answer(f'{number_of_kilos} шт. добавлено в корзину')
        return 'HANDLE_DESCRIPTION'


async def handle_cart(callback_query: types.CallbackQuery):
    if callback_query.data == 'menu':
        await send_menu(callback_query.message, 0)
        await delete_bot_message(callback_query)
        return 'HANDLE_MENU'
    elif callback_query.data == 'pay':
        text = 'Отправьте нам свой адрес или геолокацию'
        await callback_query.answer(text)
        await bot.send_message(callback_query.message.chat.id, text)
        tg_logger.debug('Start payment conversation')
        return 'WAITING_ADDRESS'
    else:
        moltin_aps.remove_item_from_cart(f'tg-{callback_query.message.chat.id}', callback_query.data)
        await send_cart(callback_query)
        await delete_bot_message(callback_query)
    return 'HANDLE_CART'


async def handle_address(message: types.Message):
    answer = 'Не могу распознать этот адресс, попробуйте ещё раз.'
    lat = lon = address_keyboard = None
    delivery_allowed = False

    if message.text:
        apikey = os.environ['GEOCODER_KEY']
        lat, lon = utils.fetch_coordinates(apikey, message.text)
    elif message.location:
        lat = message.location.latitude
        lon = message.location.longitude
    if lat:
        customer_coords = (lat, lon)
        customer_address_entry = {
            'latitude': lat,
            'longitude': lon,
        }
        coords_id = moltin_aps.add_field_entry(customer_address_entry, 'customer-address')['id']
        answer, delivery_allowed, nearest_pizzeria_id, delivery_price = get_answer_by_customer_coords(customer_coords)
        address_keyboard = collect_address_keyboard(coords_id, nearest_pizzeria_id, delivery_allowed, delivery_price)

    await bot.send_message(message.chat.id, answer, reply_markup=address_keyboard)
    if not delivery_allowed:
        return 'WAITING_ADDRESS'
    return 'WAITING_DELIVERY_CHOOSE'


def get_answer_by_customer_coords(customer_coords):
    nearest_pizzeria = utils.get_nearest_pizzeria(customer_coords)
    customer_is_close = True
    delivery_price = 0
    if nearest_pizzeria['distance'] <= 0.5:
        meters_distance = round(nearest_pizzeria['distance'] * 100)
        answer = dedent(f'''\
            Может заберете пиццу из нашей пиццерии неподолёку? Она всего в {meters_distance} метров от Вас. Вот её адресс:
            {nearest_pizzeria['address']}\n
            А можем и бесплатно доставить, нам не сложно :)
        ''')
    elif nearest_pizzeria['distance'] <= 5:
        answer = 'Похоже придется ехать до вас на самокате. Доставка будет стоить 100 рублей. Доставляем или самовывоз?'
        delivery_price = 100
    elif nearest_pizzeria['distance'] <= 20:
        answer = 'Довольно далеко до ближайшей пиццерии. Доставка будет стоить 300 рублей.'
        delivery_price = 300
    else:
        answer = dedent(f'''
        Простите, но так далеко мы пиццу не доставим. Ближайшая пиццерия в {round(nearest_pizzeria['distance'], 1)} км от вас!
        Может вы ошиблись в адресе? Попробуйте ещё раз.
        ''')
        customer_is_close = False
    return answer, customer_is_close, nearest_pizzeria['id'], delivery_price


def collect_address_keyboard(coords_id, nearest_pizzeria_id, delivery_allowed, delivery_price):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if delivery_allowed:
        keyboard.add(InlineKeyboardButton('Доставка', callback_data=f'delivery,{coords_id},{delivery_price}'))
        keyboard.add(InlineKeyboardButton('Самовывоз', callback_data=f'pickup,{nearest_pizzeria_id}'))
    return keyboard


async def handle_delivery_choose(callback_query: types.CallbackQuery):
    delivery_price = 0
    if 'pickup' in callback_query.data:
        pizzeria_id = callback_query.data.split(',')[1]
        pizzeria_address = moltin_aps.get_entry('pizzeria', pizzeria_id)['address']
        text = f'Мы начали готовить вашу пиццу. Ждём вас в нашей пиццерии по адресу:\n{pizzeria_address}'
        callback_answer = 'Ждём вас в пиццерии'
    elif 'delivery' in callback_query.data:
        coords_id, delivery_price = callback_query.data.split(',')[1:3]
        coords = moltin_aps.get_entry('customer-address', coords_id)
        coords = (coords['latitude'], coords['longitude'])
        pizzeria_id = utils.get_nearest_pizzeria(coords)['id']
        deliveryman_id = moltin_aps.get_entry('pizzeria', pizzeria_id)['deliveryman-tg-id']
        customer_cart_name = f'tg-{callback_query.message.chat.id}'
        await notify_deliveryman(deliveryman_id, customer_cart_name, delivery_price, coords[0], coords[1])
        text = 'Курьер доставит пиццу в течение 60 минут'
        callback_answer = 'Скоро пицца приедет к вам'
        dp.loop.create_task(notify_delivery_timeout(callback_query.message.chat.id))

    payment_keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton('Оплатить', callback_data=f'payment,{delivery_price}'))
    await bot.send_message(callback_query.message.chat.id, text)
    await callback_query.answer(callback_answer)
    await bot.send_message(callback_query.message.chat.id, 'Чтобы оплатить заказ, нажмите «Оплатить»',
                           reply_markup=payment_keyboard)
    return 'WAITING_PAYMENT'


async def notify_deliveryman(deliveryman_id, customer_cart_name, delivery_price, lat, lon):
    cart_items = moltin_aps.get_cart_items(customer_cart_name)
    text = f'Заказ от {customer_cart_name}:\n'
    for item in cart_items:
        text += dedent(f'''\
            {item['name']}
            {item['quantity']} шт. в корзине на сумму {item['meta']['display_price']['with_tax']['value']['formatted']}\n
        ''')
    cart_price = moltin_aps.get_cart(customer_cart_name)['meta']['display_price']['with_tax']['amount']
    total_price = int(cart_price) + int(delivery_price)
    text += f'Всего: {total_price} ₽'
    await delivery_bot.send_message(deliveryman_id, text)
    await delivery_bot.send_location(deliveryman_id, lat, lon)


async def notify_delivery_timeout(user_id):
    await sleep(300)
    # TODO check if order already delivered
    text = dedent('''\
        Время доставки подошло к концу. Мы вернем вам деньги за ваш заказ.
        Приятного аппетита!
    ''')
    await bot.send_message(user_id, text)
    # TODO return money to customer


async def handle_payment(callback_query: types.CallbackQuery):
    user_id = callback_query.message.chat.id
    goods_price = moltin_aps.get_cart(f'tg-{user_id}')['meta']['display_price']['with_tax']['amount']
    delivery_price = callback_query.data.split(',')[1]
    total_price = goods_price + int(delivery_price)
    date = int(callback_query.message.date.timestamp())
    await bot.send_invoice(user_id,
                           title='Оплата заказа',
                           description='Тестовая оплата заказа',
                           provider_token=os.environ['TG_BOT_PAYMENT_TOKEN'],
                           currency='rub',
                           prices=[types.LabeledPrice(label='rub', amount=total_price*100)],
                           start_parameter=f'{user_id}-{date}',
                           payload=f'payment-{user_id}-{date}-{total_price}'
                           )
    await callback_query.answer('Оплатите заказ')
    return 'WAITING_ADDRESS'
    # TODO waiting delivery or customer arrival


if __name__ == '__main__':
    main()
