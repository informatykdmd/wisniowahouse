from flask import Flask, render_template, redirect, url_for, jsonify, session, request, send_from_directory, g
from flask_paginate import Pagination, get_page_args
from MySQLModel import MySQLModel
import json
from bin.config_utils import SESSION_FLASK_KEY
from datetime import datetime, timedelta
from googletrans import Translator
import redis
from flask_session import Session
import logging


app = Flask(__name__)

# Klucz tajny do szyfrowania sesji
app.config['SECRET_KEY'] = SESSION_FLASK_KEY


# Ustawienia dla Flask-Session
app.config['SESSION_TYPE'] = 'redis'  # Redis jako magazyn sesji
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=10)
app.config['SESSION_KEY_PREFIX'] = 'session:'  # Prefiks dla kluczy w Redis
app.config['SESSION_REDIS'] = redis.StrictRedis(host='localhost', port=6379, db=0)

# Ustawienie ilości elementów na stronę (nie dotyczy sesji)
app.config['PER_PAGE'] = 6

# Inicjalizacja obsługi sesji
Session(app)

# Instancja MySql
def get_db():
    if 'db' not in g:
        g.db = MySQLModel(permanent_connection=False)
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close_connection()

@app.template_filter('smart_truncate')
def smart_truncate(content, length=400):
    if len(content) <= length:
        return content
    else:
        # Znajdujemy miejsce, gdzie jest koniec pełnego słowa, nie przekraczając maksymalnej długości
        truncated_content = content[:length].rsplit(' ', 1)[0]
        return f"{truncated_content}..."

translator = Translator()

def format_date(date_input, pl=True):
    ang_pol = {
        'January': 'styczeń', 'February': 'luty', 'March': 'marzec', 'April': 'kwiecień',
        'May': 'maj', 'June': 'czerwiec', 'July': 'lipiec', 'August': 'sierpień',
        'September': 'wrzesień', 'October': 'październik', 'November': 'listopad', 'December': 'grudzień'
    }

    if isinstance(date_input, str):
        # Usuwamy mikrosekundy, jeśli są
        date_input = date_input.split('.')[0]
        date_object = datetime.strptime(date_input, '%Y-%m-%d %H:%M:%S')
    else:
        date_object = date_input  # Jeśli to już datetime, używamy go bez zmian

    formatted_date = date_object.strftime('%d %B %Y')

    if pl:
        for en, pl in ang_pol.items():
            formatted_date = formatted_date.replace(en, pl)

    return formatted_date

def getLangText(text, dest='en'):
    if not text:  # Sprawdza, czy text jest pusty lub None
        return ""

    try:
        translation = translator.translate(str(text), dest=dest)
        if translation and translation.text:
            return translation.text
        else:
            return text  # Jeśli tłumaczenie zwróciło None, zwracamy oryginalny tekst
    except Exception as e:
        print(f"Error translating text: {text} - {e}")
        return text  # W razie błędu zwracamy oryginalny tekst

def generator_daneDBList(lang='pl'):
    db = MySQLModel(permanent_connection=False)  # Tworzymy instancję na czas tego wywołania

    limit = 'LIMIT 6' if lang != 'pl' else ''

    query = f"""
        SELECT 
            bp.ID, 
            c.ID as content_id, 
            ANY_VALUE(c.TITLE) as TITLE, 
            ANY_VALUE(c.CONTENT_MAIN) as CONTENT_MAIN, 
            ANY_VALUE(c.HIGHLIGHTS) as HIGHLIGHTS, 
            ANY_VALUE(c.HEADER_FOTO) as HEADER_FOTO, 
            ANY_VALUE(c.CONTENT_FOTO) as CONTENT_FOTO, 
            ANY_VALUE(c.BULLETS) as BULLETS, 
            ANY_VALUE(c.TAGS) as TAGS, 
            ANY_VALUE(c.CATEGORY) as CATEGORY, 
            ANY_VALUE(c.DATE_TIME) as DATE_TIME,
            ANY_VALUE(a.NAME_AUTHOR) as NAME_AUTHOR, 
            ANY_VALUE(a.ABOUT_AUTHOR) as ABOUT_AUTHOR, 
            ANY_VALUE(a.AVATAR_AUTHOR) as AVATAR_AUTHOR, 
            ANY_VALUE(a.FACEBOOK) as FACEBOOK, 
            ANY_VALUE(a.TWITER_X) as TWITER_X, 
            ANY_VALUE(a.INSTAGRAM) as INSTAGRAM,
            COALESCE(
                GROUP_CONCAT(
                    JSON_OBJECT(
                        'id', cm.ID, 
                        'message', cm.COMMENT_CONNTENT,  
                        'user', nw.CLIENT_NAME, 
                        'e-mail', nw.CLIENT_EMAIL, 
                        'avatar', nw.AVATAR_USER,
                        'data-time', cm.DATE_TIME
                    )
                ), '[]'
            ) as comments
        FROM blog_posts bp
        JOIN contents c ON bp.CONTENT_ID = c.ID
        JOIN authors a ON bp.AUTHOR_ID = a.ID  
        LEFT JOIN comments cm ON cm.BLOG_POST_ID = bp.ID
        LEFT JOIN newsletter nw ON nw.ID = cm.AUTHOR_OF_COMMENT_ID
        GROUP BY bp.ID
        ORDER BY bp.ID DESC
        {limit};
    """

    try:
        all_posts = db.getFrom(query, as_dict=True)
    finally:
        db.close_connection()  # Zamykamy połączenie po wykonaniu zapytania

    daneList = []

    for post in all_posts:
        comments_json = post['comments']
        comments_dict = {}

        if comments_json and comments_json.strip():
            try:
                comments_list = json.loads(f'[{comments_json}]')
                for i, comment in enumerate(comments_list):
                    if comment['message'] is not None and comment['user'] is not None:
                        comments_dict[i] = {
                            'id': comment['id'],
                            'message': comment['message'] if lang == 'pl' else getLangText(comment['message']),
                            'user': comment['user'],
                            'e-mail': comment['e-mail'],
                            'avatar': comment['avatar'],
                            'data-time': format_date(comment['data-time']) if comment['data-time'] else "Brak daty",
                        }
            except json.JSONDecodeError:
                comments_dict = {}

        bullets_list = str(post['BULLETS']).split('#splx#') if lang == 'pl' else str(getLangText(post['BULLETS'])).replace('#SPLX#', '#splx#').split('#splx#')
        tags_list = str(post['TAGS']).split(', ') if lang == 'pl' else str(getLangText(post['TAGS'])).split(', ')

        if lang != 'pl':
            post['TITLE'] = getLangText(post['TITLE'])
            post['CONTENT_MAIN'] = getLangText(post['CONTENT_MAIN'])
            post['HIGHLIGHTS'] = getLangText(post['HIGHLIGHTS'])
            post['CATEGORY'] = getLangText(post['CATEGORY'])
            post['ABOUT_AUTHOR'] = getLangText(post['ABOUT_AUTHOR'])
            post['DATE_TIME'] = format_date(post['DATE_TIME'], False)
        else:
            post['DATE_TIME'] = format_date(post['DATE_TIME'])

        theme = {
            'id': post['content_id'],
            'title': post['TITLE'],
            'introduction': post['CONTENT_MAIN'],
            'highlight': post['HIGHLIGHTS'],
            'mainFoto': post['HEADER_FOTO'],
            'contentFoto': post['CONTENT_FOTO'],
            'additionalList': bullets_list,
            'tags': tags_list,
            'category': post['CATEGORY'],
            'data': post['DATE_TIME'],
            'author': post['NAME_AUTHOR'],
            'author_about': post['ABOUT_AUTHOR'],
            'author_avatar': post['AVATAR_AUTHOR'],
            'author_facebook': post['FACEBOOK'],
            'author_twitter': post['TWITER_X'],
            'author_instagram': post['INSTAGRAM'],
            'comments': comments_dict
        }

        daneList.append(theme)

    return daneList

def generator_wisniowa_lokale():
    db = get_db()
    query_lokale = "SELECT * FROM Lokale_wisniowa;"
    all_lokale = db.getFrom(query_lokale, as_dict=True)

    for pos_dict in all_lokale:
        id_lokal = pos_dict.get('id', None)
        if isinstance(id_lokal, int):
            query_messages = f"SELECT * FROM Messages_wisniowa WHERE id_lokalu={id_lokal};"
            all_messages_for_lokal = db.getFrom(query_messages, as_dict=True)
            pos_dict['Messages'] = all_messages_for_lokal or []

    return all_lokale

nest_dict_name = {
    # Skrajne czworaki – największe ogrody
    "A1": "Nest Garden",
    "A4": "Nest Garden",
    "B1": "Nest Garden",
    "B4": "Nest Garden",

    # Bliźniaki – średnie ogrody, dobra prywatność
    "C1": "East Nest ",
    "C2": "East Nest ",
    "D1": "East Nest ",
    "D2": "East Nest ",

    # Środkowe czworaki – najmniejsze ogrody
    "A2": "Nest Compact",
    "A3": "Nest Compact",
    "B2": "Nest Compact",
    "B3": "Nest Compact"
}

@app.context_processor
def inject_shared_variable():
    all_data = generator_wisniowa_lokale()
    available_premises = {}
    sales_status = {"sold": 0, "reserved": 0, "left": 0}

    

    for ap in all_data:
        id_lokalu = ap.get('id_lokalu', '').strip()
        if not id_lokalu:
            continue

        building = id_lokalu[0].capitalize()
        if ap.get("status_lokalu") == "dostepny" and building:
            href = f"/lokale/{id_lokalu}"

            kind_nest = nest_dict_name.get(id_lokalu, '')
            name = f"{kind_nest} {id_lokalu}"

            id_direct = ap.get('id')

            building_key = f"Budynek {building}"
            available_premises.setdefault(building_key, []).append({
                "href": href,
                "name": name,
                "id_direct": id_direct
            })
        
        if ap.get("status_lokalu") == "dostepny":
            sales_status["left"] += 1
        elif ap.get("status_lokalu") == "sprzedane":
            sales_status["sold"] += 1
        elif ap.get("status_lokalu") == "rezerwacja":
            sales_status["reserved"] += 1

    return {
        'available_premises': available_premises,
        "sales_status": sales_status
    }

logFileName = '/home/johndoe/app/wisniowahouse/logs/access.log'  # 🔁 ZMIENIAJ dla każdej aplikacji

# Konfiguracja loggera
logging.basicConfig(filename=logFileName, level=logging.INFO,
                    format='%(asctime)s - %(message)s', filemode='a')

# Funkcja do logowania informacji o zapytaniu
def log_request():
    ip_address = request.remote_addr
    date_time = datetime.now()
    endpoint = request.endpoint or request.path  # fallback jeśli brak endpointu
    method = request.method

    logging.info(f'IP: {ip_address}, Time: {date_time}, Endpoint: {endpoint}, Method: {method}')

@app.before_request
def before_request_logging():
    log_request()


############################
##      ######           ###
##      ######           ###
##     ####              ###
##     ####              ###
##    ####               ###
##    ####               ###
##   ####                ###
##   ####                ###
#####                    ###
#####                    ###
##   ####                ###
##   ####                ###
##    ####               ###
##    ####               ###
##     ####              ###
##     ####              ###
##      ######           ###
##      ######           ###
############################


# Strona główna
@app.route('/')
def index():
    session['page'] = 'index'
    pageTitle = 'Strona Główna'

    # posts = generator_daneDBList()

    return render_template(
        'index.html',
        pageTitle=pageTitle,
        # posts=posts
    )

# Lokale
@app.route('/lokale')
def lokale():
    session['page'] = 'lokale'
    pageTitle = 'Lokale'

    db = get_db()
    query_lokale = """
        SELECT 
            id,
            id_lokalu,
            nazwa,
            opis,
            powierzchnia_m2,
            powierzchnia_uzytkowa_m2,
            cena_wyjsciowa,
            status_lokalu,
            typ_zabudowy,
            umiejscowienie
        FROM Lokale_wisniowa;
    """
    all_data = db.getFrom(query_lokale, as_dict=True)
    # nest_dict_name = {
    #     # Skrajne czworaki – największe ogrody
    #     "A1": "Nest Garden",
    #     "A4": "Nest Garden",
    #     "B1": "Nest Garden",
    #     "B4": "Nest Garden",

    #     # Bliźniaki – średnie ogrody, dobra prywatność
    #     "C1": "East Nest ",
    #     "C2": "East Nest ",
    #     "D1": "East Nest ",
    #     "D2": "East Nest ",

    #     # Środkowe czworaki – najmniejsze ogrody
    #     "A2": "Nest Compact",
    #     "A3": "Nest Compact",
    #     "B2": "Nest Compact",
    #     "B3": "Nest Compact"
    # }

    lokale_dict = {}

    for ap in all_data:
        id_lokalu = ap.get('id_lokalu', '').strip()
        if not id_lokalu:
            continue
        

        building = id_lokalu[0].capitalize()
        if building:
            href = f"/lokale/{id_lokalu}"
            id_direct = ap.get('id')
            status_lokalu = ap.get('status_lokalu')
            cena_wyjsciowa = ap.get('cena_wyjsciowa')
            powierzchnia_uzytkowa_m2 = ap.get('powierzchnia_uzytkowa_m2')
            title = ap.get('nazwa')
            kind_nest = nest_dict_name.get(id_lokalu, '')

            name = f"{kind_nest} {id_lokalu} {powierzchnia_uzytkowa_m2} m²"

            if id_lokalu not in lokale_dict:
                lokale_dict[id_lokalu] = {
                    "href": href,
                    "title": title,
                    "name": name,
                    "id_direct": id_direct,
                    "id_lokalu": id_lokalu,
                    "status_lokalu": status_lokalu,
                    "cena_wyjsciowa": cena_wyjsciowa,
                    "powierzchnia_uzytkowa_m2": powierzchnia_uzytkowa_m2
                }

    return render_template(
        'lokale.html',
        pageTitle=pageTitle,
        lokale_dict=lokale_dict
    )

@app.route('/lokale/<category>')
def lokale_details(category):
    session['page'] = f'lokal_{category}'
    pageTitle = f'Lokale - {category.capitalize()}'

    db = get_db()
    query_lokale = """
        SELECT 
            id,
            id_lokalu,
            nazwa,
            opis,
            powierzchnia_m2,
            powierzchnia_uzytkowa_m2,
            cena_wyjsciowa,
            status_lokalu,
            typ_zabudowy,
            umiejscowienie
        FROM Lokale_wisniowa 
        WHERE id_lokalu=%s;
    """
    result = db.getFrom(query_lokale, (category.capitalize(), ), as_object=True)
    lokal_data = result[0] if result else {}

    # Zabezpieczenie: jeśli brak lokalu lub jest zarezerwowany/sprzedany, przekieruj
    if not lokal_data or lokal_data.status_lokalu.lower() in ['sprzedane', 'rezerwacja']:
        return redirect(url_for('lokale'))  # zakładam że taka funkcja istnieje
    

    return render_template(
        'lokal.html',
        pageTitle=pageTitle,
        lokal_data=lokal_data
    )

@app.route('/pobierz/<filename>')
def download_file(filename):
    return send_from_directory('static/downloads', filename, as_attachment=True)


@app.route('/api/lokale', methods=['GET'])
def get_lokale():
    db = get_db()
    query_lokale = """
        SELECT 
            id_lokalu,
            nazwa,
            opis,
            powierzchnia_m2,
            powierzchnia_uzytkowa_m2,
            cena_wyjsciowa,
            status_lokalu,
            typ_zabudowy,
            umiejscowienie
        FROM Lokale_wisniowa;
    """
    result = db.getFrom(query_lokale, as_dict=True)
    for lok in result:
        if "id_lokalu" in lok:
            id_lokalu = lok["id_lokalu"]
            kind_nest = nest_dict_name.get(id_lokalu, '')
            name = f"{kind_nest} {id_lokalu} "
            lok["name"] = name

    return jsonify(result)

# Wizualizacje
@app.route('/wizualizacje')
def wizualizacje():
    session['page'] = 'wizualizacje'
    pageTitle = 'Wizualizacje'
    return render_template(
        'wizualizacje.html',
        pageTitle=pageTitle
    )

# Lokalizacja
@app.route('/lokalizacja')
def lokalizacja():
    session['page'] = 'lokalizacja'
    pageTitle = 'Lokalizacja'

    return render_template(
        'lokalizacja.html',
        pageTitle=pageTitle
    )

# O inwestycji
@app.route('/o-inwestycji')
def o_inwestycji():
    session['page'] = 'o_inwestycji'
    pageTitle = 'O Inwestycji'

    return render_template(
        'o_inwestycji.html',
        pageTitle=pageTitle
    )

@app.route('/o-inwestycji/<detail>')
def o_inwestycji_detail(detail):

    details_allowed = [
        'standard-wykonczenia', 'technologie-budowlane',
        'zalety-lokalizacji', 'plan-osiedla'
    ]

    if detail in details_allowed:
        session['page'] = f'o_inwestycji_{detail}'
        pageTitle = f'O Inwestycji - {detail.capitalize()}'

        return render_template(
            'o_inwestycji_detail.html',
            pageTitle=pageTitle,
            detail=detail
        )
    
    pageTitle = 'O Inwestycji'
    return render_template(
        'o_inwestycji.html',
        pageTitle=pageTitle
    )
    

# O firmie
@app.route('/o-firmie')
def o_firmie():
    session['page'] = 'o_firmie'
    pageTitle = 'O Firmie'

    return render_template(
        'o_firmie.html',
        pageTitle=pageTitle
    )

# Kontakt
@app.route('/kontakt')
def kontakt():
    session['page'] = 'kontakt'
    pageTitle = 'Kontakt'

    return render_template(
        'kontakt.html',
        pageTitle=pageTitle
    )

# Dodatkowe strony
@app.route('/architektura')
def architektura():
    session['page'] = 'architektura'
    pageTitle = 'Nowoczesna Architektura'

    return render_template(
        'architektura.html',
        pageTitle=pageTitle
    )

@app.route('/dni-otwarte')
def dni_otwarte():
    session['page'] = 'dni_otwarte'
    pageTitle = 'Dni Otwarte'

    return render_template(
        'dni_otwarte.html',
        pageTitle=pageTitle
    )


@app.route('/kontrola-jakosci')
def kontrola_jakosci():
    session['page'] = 'kontrola_jakosci'
    pageTitle = 'Kontrola Jakości'

    return render_template(
        'kontrola_jakosci.html',
        pageTitle=pageTitle
    )

@app.route('/proces-zakupu')
def proces_zakupu():
    session['page'] = 'proces_zakupu'
    pageTitle = 'Proces Zakupu'

    return render_template(
        'proces_zakupu.html',
        pageTitle=pageTitle
    )

@app.route('/eco-technologie')
def eco_technologie():
    session['page'] = 'eco_technologie'
    pageTitle = 'Technologie Eco'

    return render_template(
        'eco_technologie.html',
        pageTitle=pageTitle
    )

@app.route('/standard')
def standard():
    session['page'] = 'standard'
    pageTitle = 'Standard Wykończenia'

    return render_template(
        'standard.html',
        pageTitle=pageTitle
    )

@app.route('/zakup')
def zakup():
    session['page'] = 'zakup'
    pageTitle = 'Zakup Lokalu'

    return render_template(
        'zakup.html',
        pageTitle=pageTitle
    )

@app.route('/wykonawca')
def wykonawca():
    session['page'] = 'wykonawca'
    pageTitle = 'Wykonawca'

    return render_template(
        'wykonawca.html',
        pageTitle=pageTitle
    )

@app.route('/polityka-prywatnosci')
def polityka_prywatnosci():
    session['page'] = 'polityka_prywatnosci'
    pageTitle = 'Polityka Prywatności'

    return render_template(
        'polityka_prywatnosci.html',
        pageTitle=pageTitle
    )

@app.errorhandler(404)
def page_not_found(e):
    # Tutaj możesz przekierować do dowolnej trasy, którą chcesz wyświetlić jako stronę błędu 404.
    return redirect(url_for(f'index'))


@app.route('/subpage', methods=['GET'])
def subpage():
    session['page'] = 'subpage'
    pageTitle = 'subpage'

    if 'target' in request.args:
        if request.args['target'] in ['polityka', 'zasady', 'pomoc', 'faq']:
            targetPage = request.args['target']
            pageTitle = targetPage
        else: 
            targetPage = "pomoc"
            pageTitle = targetPage
    else:
        targetPage = "pomoc"
        pageTitle = targetPage

    return render_template(
        f'{targetPage}.html',
        pageTitle=pageTitle
        )

@app.route('/api/contact', methods=['POST'])
def contact():
    name = request.form.get('name')
    email = request.form.get('email')
    lokal = request.form.get('lokal')
    phone = request.form.get('phone')
    title = request.form.get('title', 'Wiadomość ze strony')  # fallback tytuł
    message = request.form.get('message', '')  # pusty string jeśli brak wiadomości

    if not name or not email or not lokal or not phone:
        return jsonify({'message': 'Brakuje wymaganych danych'}), 400

    print(f"Otrzymano formularz: {name}, {email}, {lokal}, {phone}")

    db = get_db()
    query = """
        INSERT INTO Messages_wisniowa (
            id_lokalu,
            tytul_wiadomosci,
            wiadomosc,
            autor_wiadomosci,
            email_autora_wiadomosci,
            telefon_do_autora_wiadomosci,
            status_wiadomosci
        ) VALUES (%s, %s, %s, %s, %s, %s, 'nowa');
    """
    params = (lokal, title, message, name, email, phone)

    success = db.executeTo(query, params)

    if success:
        return jsonify({'message': 'Dane odebrane poprawnie'}), 200
    else:
        return jsonify({'message': 'Błąd serwera MySQL!'}), 500



if __name__ == '__main__':
    # app.run(debug=True, port=5090)
    app.run(debug=True, host='0.0.0.0', port=5090)