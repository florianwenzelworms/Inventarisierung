from flask import Flask, render_template, flash, redirect, url_for, request, send_file

app = Flask(__name__)
app.config["SECRET_KEY"] = 'e79b9847144221ba4e85df9dd483a3e5'


@app.route('/', methods=["GET", "POST"])
def home():
    return render_template('main.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
