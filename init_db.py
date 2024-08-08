from app import app, db, User

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        #db.session.add(User(id=1, username="wenzelf", email="florian.wenzel@worms.de", password="Fjbteam123"))
        #db.session.commit()


