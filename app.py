from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import json
import re
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

migrate = Migrate(app, db)

class Saldo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float, nullable=False)

class Magazyn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produkt = db.Column(db.String(80), nullable=False)
    ilosc = db.Column(db.Integer, nullable=False)
    cena = db.Column(db.Float, nullable=False)

class Historia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wpis = db.Column(db.String(200), nullable=False)

with app.app_context():
    db.create_all()
    if not Saldo.query.first():
        db.session.add(Saldo(value=0))
        db.session.commit()

# funkcja do odczytywania danych z bazy danych
def load_data():
    saldo_record = Saldo.query.first()
    if saldo_record is None:
        saldo = 0
    else:
        saldo = saldo_record.value
    magazyn = {}
    for row in Magazyn.query.all():
        magazyn[row.produkt] = {"ilosc": row.ilosc, "cena": row.cena}
    historia = [row.wpis for row in Historia.query.all()]
    return saldo, magazyn, historia


# funkcja do zapisywania danych do bazy danych
def save_data(saldo, magazyn, historia):
    db_saldo = Saldo.query.first()
    db_saldo.value = saldo
    Magazyn.query.delete()
    for produkt, dane in magazyn.items():
        db.session.add(Magazyn(produkt=produkt, ilosc=dane["ilosc"], cena=dane["cena"]))
    Historia.query.delete()
    for wpis in historia:
        db.session.add(Historia(wpis=wpis))
    db.session.commit()

def load_data_from_txt():
    with open("saldo.txt", "r") as saldo_file:
        saldo = float(saldo_file.read().strip())

    magazyn = {}
    with open("magazyn.txt", "r") as magazyn_file:
        for line in magazyn_file:
            produkt, ilosc, cena = line.strip().split(';')
            magazyn[produkt] = {"ilosc": int(ilosc), "cena": float(cena)}

    historia = []
    with open("historia.txt", "r") as historia_file:
        for line in historia_file:
            historia.append(line.strip())

    return saldo, magazyn, historia

def initialize_database():
    saldo, magazyn, historia = load_data_from_txt()

    with app.app_context():
        db.create_all()

        if not Saldo.query.first():
            db.session.add(Saldo(value=saldo))

        for produkt, dane in magazyn.items():
            db.session.add(Magazyn(produkt=produkt, ilosc=dane["ilosc"],
                                   cena=dane["cena"]))

        for wpis in historia:
            db.session.add(Historia(wpis=wpis))

        db.session.commit()

@app.route('/')
def index():
    saldo, magazyn, _ = load_data()
    return render_template('index.html', saldo=saldo, magazyn=magazyn)

@app.route('/zakup', methods=['GET', 'POST'])
def zakup():
    if request.method == 'POST':
        nazwa = request.form['nazwa']
        cena = float(request.form['cena'])
        ilosc = int(request.form['ilosc'])
        saldo, magazyn, historia = load_data()
        if saldo >= cena * ilosc:
            saldo -= cena * ilosc
            if nazwa in magazyn:
                magazyn[nazwa] = {"ilosc": magazyn.get(nazwa, {"ilosc": 0})["ilosc"]
                                           + ilosc, "cena": cena}
            else:
                magazyn[nazwa] = {"ilosc": ilosc, "cena": cena}
            current_date = datetime.now().strftime("%Y-%m-%d")
            historia.append(f'{current_date} Zakup: {nazwa}, cena: {cena}, ilość:'
                            f' {ilosc}\n')
            save_data(saldo, magazyn, historia)
            return redirect(url_for('index'))
        else:
            return render_template('zakup.html', error='Brak środków na koncie')
    else:
        return render_template('zakup.html')

@app.route('/sprzedaz', methods=['POST'])
def sprzedaz():
    nazwa = request.form['nazwa']
    ilosc = int(request.form['ilosc'])
    cena = float(request.form['cena'])

    saldo, magazyn, historia = load_data()

    if nazwa in magazyn and magazyn[nazwa]['ilosc'] >= ilosc:
        magazyn[nazwa]['ilosc'] -= ilosc
        saldo += cena * ilosc
        current_date = datetime.now().strftime("%Y-%m-%d")
        historia.append(f'{current_date} Sprzedaż: {nazwa}, cena: {cena}, '
                        f'ilość: {ilosc}\n')
        save_data(saldo, magazyn, historia)
        return redirect(url_for('index'))
    else:
        return render_template('index.html', error='Nie można sprzedać towaru')

@app.route('/saldo', methods=['POST'])
def update_saldo():
    zmiana = float(request.form['zmiana'])
    saldo, magazyn, historia = load_data()
    saldo += zmiana
    current_date = datetime.now().strftime("%Y-%m-%d")
    historia.append(f'{current_date} Zmiana salda: {zmiana}\n')
    save_data(saldo, magazyn, historia)
    return redirect(url_for('index'))

@app.route('/historia/', defaults={'start': None, 'end': None})
@app.route('/historia/<int:start>/<int:end>')
def historia(start, end):
    _, _, historia = load_data()
    if start is not None and end is not None:
        if 0 <= start < len(historia) and 0 <= end <= len(historia):
            historia = historia[start:end]
        else:
            error_msg = f"Nieprawidłowy zakres indeksów. Możliwy zakres to " \
                        f"od 0 do {len(historia) - 1}."
            return render_template('historia.html', error=error_msg)

    parsed_history = []
    for entry in historia:
        entry_parts = entry.split(' ', 1)
        if len(entry_parts) < 2:
            continue
        date, operation = entry_parts
        parsed_history.append({
            'data': date,
            'typ': operation.split(':')[0].strip(),
            'produkt': re.findall(r'([a-zA-Z\s]+),', operation)[0].strip() if
            re.findall(r'([a-zA-Z\s]+),', operation) else '',
            'ilosc': int(re.findall(r'ilość:\s(\d+)', operation)[0]) if
            re.findall(r'ilość:\s(\d+)', operation) else 0,
            'cena': float(re.findall(r'cena:\s([0-9.]+)', operation)[0]) if
            re.findall(r'cena:\s([0-9.]+)', operation) else 0
        })
    return render_template('historia.html', historia=parsed_history)

if __name__ == '__main__':
    with app.app_context():
        initialize_database()
    app.run(debug=True)

