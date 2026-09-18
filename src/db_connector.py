from arango import ArangoClient


def get_database(
    host="http://localhost:8529",
    database="yelp",
    username="root",
    password="root"
):
    client = ArangoClient(hosts=host)

    db = client.db(
        database,
        username=username,
        password=password
    )

    return db