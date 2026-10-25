from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.sql import func
from passlib.handlers.sha2_crypt import sha512_crypt as crypto
from . import models, schemas
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import csv
from .vars import *
from os import remove, path
import uuid


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def get_users(db: Session, skip: int = 0, limit: int = 50):
    return db.query(models.User).offset(skip).limit(limit).all()

def list_library_users(db: Session):
    return db.query(models.User).order_by(models.User.username.asc()).all()

def list_local_patrons(db: Session):
    return db.query(models.User).filter(models.User.isAdmin == False).order_by(
        models.User.surname1.asc(), models.User.givenName.asc()
    ).all()

def library_theme(db: Session | None = None) -> str:
    own_session = db is None
    if own_session:
        from .database import SessionLocal
        db = SessionLocal()
    try:
        config = db.query(models.config).first()
        theme = (config.theme or "light") if config else "light"
        return theme if theme in ("light", "dark") else "light"
    except Exception:
        return "light"
    finally:
        if own_session:
            db.close()

def ebooks_enabled(db: Session | None = None) -> bool:
    own_session = db is None
    if own_session:
        from .database import SessionLocal
        db = SessionLocal()
    try:
        config = db.query(models.config).first()
        return bool(config and config.ebooksEnabled)
    except Exception:
        return False
    finally:
        if own_session:
            db.close()

def patron_self_service_enabled(db: Session | None = None) -> bool:
    own_session = db is None
    if own_session:
        from .database import SessionLocal
        db = SessionLocal()
    try:
        config = db.query(models.config).first()
        return bool(config and config.patronSelfService)
    except Exception:
        return False
    finally:
        if own_session:
            db.close()

def ensure_schema():
    """Add columns that create_all does not add to an existing SQLite file."""
    conn = sqlite3.connect(DB_LOCATION)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "users" in tables:
            user_columns = {row[1] for row in conn.execute("PRAGMA table_info('users')")}
            for column in (
                "givenName", "surname1", "surname2", "province", "canton",
                "district", "address", "phone", "email",
            ):
                if column not in user_columns:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {column} VARCHAR")
        if "books" in tables:
            book_columns = {row[1] for row in conn.execute("PRAGMA table_info('books')")}
            for column, declaration in (
                ("publisher", "VARCHAR"),
                ("pages", "INTEGER"),
                ("copies", "INTEGER"),
                ("available", "INTEGER"),
            ):
                if column not in book_columns:
                    conn.execute(f"ALTER TABLE books ADD COLUMN {column} {declaration}")
            conn.execute("UPDATE books SET copies = 1 WHERE copies IS NULL")
            conn.execute(
                "UPDATE books SET available = CASE WHEN withdrawn = 1 THEN 0 ELSE COALESCE(copies, 1) END "
                "WHERE available IS NULL"
            )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS loans ("
            "id INTEGER PRIMARY KEY, bookId INTEGER, username VARCHAR, active BOOLEAN DEFAULT 1)"
        )
        conn.execute(
            "INSERT INTO loans (bookId, username, active) "
            "SELECT id, withdrawnBy, 1 FROM books "
            "WHERE withdrawn = 1 AND withdrawnBy IS NOT NULL AND withdrawnBy != '' "
            "AND id NOT IN (SELECT bookId FROM loans WHERE active = 1)"
        )
        if "config" in tables:
            config_columns = {row[1] for row in conn.execute("PRAGMA table_info('config')")}
            if "patronSelfService" not in config_columns:
                conn.execute("ALTER TABLE config ADD COLUMN patronSelfService BOOLEAN DEFAULT 0")
                conn.execute("UPDATE config SET patronSelfService = 0 WHERE patronSelfService IS NULL")
            if "ebooksEnabled" not in config_columns:
                conn.execute("ALTER TABLE config ADD COLUMN ebooksEnabled BOOLEAN DEFAULT 0")
                conn.execute("UPDATE config SET ebooksEnabled = 0 WHERE ebooksEnabled IS NULL")
            if "theme" not in config_columns:
                conn.execute("ALTER TABLE config ADD COLUMN theme VARCHAR DEFAULT 'light'")
            conn.execute("UPDATE config SET theme = 'light' WHERE theme IS NULL OR theme = ''")
        conn.commit()
    finally:
        conn.close()

def create_user(db: Session, user: schemas.UserCreate):
    try:
        passhash = crypto.hash(str(user.password))
        db_user = models.User(
            username=user.username,
            passhash=passhash,
            isAdmin=user.isAdmin,
            givenName=user.givenName,
            surname1=user.surname1,
            surname2=user.surname2,
            province=user.province,
            canton=user.canton,
            district=user.district,
            address=user.address,
            phone=user.phone,
            email=user.email,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        print(e)
        return False
        
def isAdmin(db: Session, username: str):
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        return User.isAdmin
    except Exception as e:
        print(e)
        return False
        


def createBook(db: Session, book: schemas.Book):
    try:
        book = models.Book(** book.model_dump(exclude_none=True))
        db.add(book)
        db.commit()
        db.refresh(book)
        return "True"
    except Exception as e:
        print(e)
        return "False"
        
def deleteBook(db: Session, bookId):
    try:
        purgeFromReadingList(db, bookId)
        purgeFromImages(db, bookId)
        purgeFromEbooks(db, bookId)
        book = db.query(models.Book).filter(models.Book.id == bookId).first()
        db.delete(book)
        db.commit()
        return "True"
    except Exception as e:
        print(e)
        return "False"
 
def stock_of(book):
    copies = book.copies if book.copies is not None else 1
    if book.available is None:
        available = 0 if book.withdrawn else copies
    else:
        available = book.available
    return copies, available


def lend_copy(db: Session, book, username: str) -> bool:
    copies, available = stock_of(book)
    if available < 1:
        return False
    book.copies = copies
    book.available = available - 1
    book.withdrawn = book.available == 0
    book.withdrawnBy = username
    db.add(models.Loan(bookId=book.id, username=username, active=True))
    db.commit()
    return True


def return_loan(db: Session, loan) -> bool:
    if not loan or not loan.active:
        return False
    book = db.get(models.Book, loan.bookId)
    if not book:
        return False
    loan.active = False
    copies, available = stock_of(book)
    book.copies = copies
    book.available = min(copies, available + 1)
    book.withdrawn = book.available == 0
    next_loan = db.query(models.Loan).filter(
        models.Loan.bookId == book.id,
        models.Loan.active == True,
        models.Loan.id != loan.id,
    ).order_by(models.Loan.id.desc()).first()
    book.withdrawnBy = next_loan.username if next_loan else None
    db.commit()
    return True


def active_loans(db: Session, book_id=None):
    query = db.query(models.Loan).filter(models.Loan.active == True)
    if book_id is not None:
        query = query.filter(models.Loan.bookId == book_id)
    return query.order_by(models.Loan.id.asc()).all()


def import_catalog(db: Session, rows: list[list[str]]):
    from .spreadsheet import catalog_rows
    created = updated = skipped = 0
    existing = db.query(models.Book).all()

    def same(book, title, author):
        return " ".join((book.title or "").casefold().split()) == title and " ".join((book.author or "").casefold().split()) == author

    for item in catalog_rows(rows):
        if not item["title"]:
            skipped += 1
            continue
        quantity = item["quantity"] if item["quantity"] is not None else 1
        if quantity < 1:
            skipped += 1
            continue
        title_key = " ".join(item["title"].casefold().split())
        author_key = " ".join(item["author"].casefold().split())
        match = next((book for book in existing if same(book, title_key, author_key)), None)
        if match:
            copies, available = stock_of(match)
            match.copies = copies + quantity
            match.available = available + quantity
            match.withdrawn = match.available == 0
            if item["publisher"]:
                match.publisher = item["publisher"]
            if item["pages"] is not None:
                match.pages = item["pages"]
            updated += 1
        else:
            book = models.Book(
                title=item["title"],
                author=item["author"] or None,
                publisher=item["publisher"] or None,
                pages=item["pages"],
                copies=quantity,
                available=quantity,
                owned=True,
                withdrawn=False,
                ebook=False,
            )
            db.add(book)
            existing.append(book)
            created += 1
    db.commit()
    return created, updated, skipped


def getBookById(db: Session, bookId):
    try:
        return db.query(models.Book).filter(models.Book.id == bookId).first()
    except Exception as e:
        print(e)
        return False
                
def updateBook(db: Session, book: schemas.Book):
    try:
        item = db.get(models.Book, book.id) 
        if item:
            book = models.Book(** book.model_dump())
            db.merge(book)
            db.commit()   
        if not item:
            print("updated item does not exist")
            return False
    except Exception as e:
        print(e)
        return False
        
def getBooks(db: Session, skip: int = 0, limit: int = 50):
    result = db.query(models.Book).offset(skip).limit(limit).all()
    resultCount = db.query(models.Book).with_entities(func.count()).scalar()
    return result, resultCount
  
  
  
    
def searchBooks(db: Session, title, author, skip: int, onlyEbooks: bool, noEbooks:bool, limit: int = 50):
    if (onlyEbooks==True) and (noEbooks==False):
        resultCount = db.query(models.Book).filter(
    (or_(models.Book.title.icontains(title),
    models.Book.author.icontains(author)) & (models.Book.owned==True) & (models.Book.ebook==True))).with_entities(func.count()).scalar()
        result = db.query(models.Book).filter(
    (or_(models.Book.title.icontains(title),
    models.Book.author.icontains(author)) & (models.Book.owned==True) & (models.Book.ebook==True))).order_by(models.Book.title.asc()).limit(limit).offset(skip).all()
        return result, resultCount
    elif (onlyEbooks==False) and (noEbooks==True):
         resultCount = db.query(models.Book).filter(
    (or_(models.Book.title.icontains(title),
    models.Book.author.icontains(author)) & (models.Book.owned==True) & (models.Book.ebook==False))).with_entities(func.count()).scalar()
         result = db.query(models.Book).filter(
    (or_(models.Book.title.icontains(title),
    models.Book.author.icontains(author)) & (models.Book.owned==True) & (models.Book.ebook==False))).order_by(models.Book.title.asc()).limit(limit).offset(skip).all()
         return result, resultCount
    else:
        resultCount = db.query(models.Book).filter(
    or_(models.Book.title.icontains(title),
    models.Book.author.icontains(author)) & (models.Book.owned==True)).with_entities(func.count()).scalar()
        result = db.query(models.Book).filter(
    or_(models.Book.title.icontains(title),
    models.Book.author.icontains(author)) & (models.Book.owned==True)).order_by(models.Book.title.asc()).limit(limit).offset(skip).all()
        return result, resultCount

def searchBooksbyAuthor(db: Session, author, skip: int, onlyEbooks: bool, noEbooks:bool, limit: int = 50):
    if (onlyEbooks==True) and (noEbooks==False):
        resultCount = db.query(models.Book).filter(
    models.Book.author.icontains(author) & (models.Book.owned==True) & (models.Book.ebook==True)).with_entities(func.count()).scalar()
        result = db.query(models.Book).filter(
    models.Book.author.icontains(author) & (models.Book.owned==True) & (models.Book.ebook==True)).order_by(models.Book.author.asc()).limit(limit).offset(skip).all()
        return result, resultCount
    elif (onlyEbooks==False) and (noEbooks==True):
        result = db.query(models.Book).filter(
    models.Book.author.icontains(author) & (models.Book.owned==True) & (models.Book.ebook==False)).order_by(models.Book.author.asc()).limit(limit).offset(skip).all()
        resultCount = db.query(models.Book).filter(
    models.Book.author.icontains(author) & (models.Book.owned==True) & (models.Book.ebook==False)).with_entities(func.count()).scalar()
        return result, resultCount
    else:
        result = db.query(models.Book).filter(
    models.Book.author.icontains(author) & (models.Book.owned==True)).order_by(models.Book.author.asc()).limit(limit).offset(skip).all()
        resultCount = db.query(models.Book).filter(
    models.Book.author.icontains(author) & (models.Book.owned==True)).with_entities(func.count()).scalar()
        return result, resultCount

def searchBooksbyTitle(db: Session, title, skip: int, onlyEbooks: bool, noEbooks:bool, limit: int = 50):
    if (onlyEbooks==True) and (noEbooks==False):
        result = db.query(models.Book).filter(
    models.Book.title.icontains(title) & (models.Book.owned==True) & (models.Book.ebook==True)).order_by(models.Book.title.asc()).limit(limit).offset(skip).all()
        resultCount = db.query(models.Book).filter(
    models.Book.title.icontains(title) & (models.Book.owned==True) & (models.Book.ebook==True)).with_entities(func.count()).scalar()
        return result, resultCount    
    elif (onlyEbooks==False) and (noEbooks==True):
        result = db.query(models.Book).filter(
    models.Book.title.icontains(title) & (models.Book.owned==True) & (models.Book.ebook==False)).order_by(models.Book.title.asc()).limit(limit).offset(skip).all()
        resultCount = db.query(models.Book).filter(
    models.Book.title.icontains(title) & (models.Book.owned==True) & (models.Book.ebook==False)).with_entities(func.count()).scalar()
        return result, resultCount
    else:
        result = db.query(models.Book).filter(
    models.Book.title.icontains(title) & (models.Book.owned==True)).order_by(models.Book.title.asc()).limit(limit).offset(skip).all()    
        resultCount = db.query(models.Book).filter(
    models.Book.title.icontains(title) & (models.Book.owned==True)).with_entities(func.count()).scalar()
        return result, resultCount

def browseBooksByGenre(db: Session, genre):
    return db.query(models.Book).filter(models.Book.genre == genre)

def browseWishlist(db: Session):
    return db.query(models.Book).filter(models.Book.owned == False)
    
def browseWithdrawn(db: Session):
    return db.query(models.Book).filter(models.Book.withdrawn == True)
    
def getGenres(db: Session):
    genres = []
    for value in db.query(models.Book.genre).distinct():
        genres.append(value[0])
    return genres
    
def readBook(db: Session, readingListItem: schemas.readingListItemCreate):
    try:
        readingListItem = models.readingListItems(** readingListItem.model_dump())
        db.add(readingListItem)
        db.commit()
        db.refresh(readingListItem)
        return "True"
    except Exception as e:
        print(e)
        return "False"
        
def readingList(db: Session, userId: int):  
    return db.query(models.readingListItems).filter(models.readingListItems.user_id == userId).all()
    
def bookUnRead(db: Session, bookId):
    try:
        readingListItem = db.query(models.readingListItems).filter(models.readingListItems.book == bookId).first()
        db.delete(readingListItem)
        db.commit()  
        return True
    except Exception as e:
        print(e)
        return False
        
def purgeFromReadingList(db: Session, bookId):
    try:
        book = db.query(models.readingListItems).filter(models.readingListItems.book == bookId).all()
        for i in book:
            db.delete(i)
        db.commit()  
        return True
    except Exception as e:
        print(e)
        return False

def purgeFromImages(db: Session, bookId):
    try:
        book = db.query(models.bookImage).filter(models.bookImage.bookId == bookId).all()
        for i in book:
            jpgPath = os.path.join('./static/bookImages/', str(i.filename) + ".jpg")
            thumbPath = os.path.join('./static/bookImages/', str(i.filename) + "_thumbnail.jpg")
            if os.path.isfile(thumbPath):
                os.remove(thumbPath)
            if os.path.isfile(jpgPath):    
                os.remove(jpgPath)  
            db.delete(i)
        db.commit()
        return True
    except Exception as e:
        print(e)
        return False

def purgeFromEbooks(db: Session, bookId):
    try:
        book = db.query(models.ebook).filter(models.ebook.bookId == bookId).all()
        for i in book:
            ebookPath = os.path.join('./static/eBooks/', str(i.filename))
            if os.path.isfile(ebookPath):
                os.remove(ebookPath)
            db.delete(i)
        db.commit()  
        return True
    except Exception as e:
        print(e)
        return False

def bookReturn(db: Session, book: schemas.Book):
    try:  
        item = db.get(models.Book, book.id)  
        if item:
            book = models.Book(** book.model_dump())
            db.merge(book)
            db.commit()   
        if not item:
            print("updated item does not exist")
            return False
    except Exception as e:
        print(e)
        return False

def bookWithdraw(db: Session, book: schemas.Book):
    try:
        item = db.get(models.Book, book.id)  
        if item:
            book = models.Book(** book.model_dump())
            db.merge(book)
            db.commit()   
        if not item:
            print("updated item does not exist")
            return False
    except Exception as e:
        print(e)
        return False
        
def wipeAndRestore(filename):
    conn = sqlite3.connect(DB_LOCATION)
    cursor = conn.execute("DROP TABLE IF EXISTS 'books';")
    cursor = conn.execute("DROP TABLE IF EXISTS 'ebooks';")
    cursor = conn.execute("DROP TABLE IF EXISTS 'userEmails';")
    cursor = conn.execute("DROP TABLE IF EXISTS 'readinglistitems';")
    cursor = conn.execute("DROP TABLE IF EXISTS 'users';")
    cursor = conn.execute("DROP TABLE IF EXISTS 'bookImages';")
    cursor = conn.execute("DROP TABLE IF EXISTS 'config';")
    cursor = conn.execute("DROP TABLE IF EXISTS 'links';")
    cursor = conn.execute("DROP TABLE IF EXISTS 'vkeys';")
    cursor.close()
    conn.commit()
    f = open(filename,'r')
    sql = f.read() # watch out for built-in `str`
    cursor = conn.executescript(sql)
    cursor.close()
    conn.commit()
    conn.close()
    return
    
def addCSV(filename):
    with open(filename,'r') as booksCSV: 
        books = csv.DictReader(booksCSV, fieldnames=['id','title','author','summary','genre','library','shelf','collection','ISBN','notes','owned','withdrawn']) 
        addBooks = [(i['title'], i['author'], i['summary'], i['genre'], i['library'], i['shelf'], i['collection'], i['ISBN'], i['notes'], i['owned'], i['withdrawn']) for i in books]
        print(type(addBooks))
    conn = sqlite3.connect(DB_LOCATION)
    cur = conn.cursor()
    cur.executemany("INSERT INTO books (title, author, summary, genre, library, shelf, collection, ISBN, notes, owned, withdrawn) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", addBooks)
    conn.commit()
    conn.close() 
    return

def checkDB():
    conn = sqlite3.connect(DB_LOCATION)
    configExists = conn.execute("PRAGMA table_info('books');").fetchall()
    if configExists[4][1] == "coverImage":
        return False
    else:
        return True


def updateDB():
    #This updates the DB version from (unversioned) to 1.0.0. Mostly, creating tables will be handled automatically on startup but altering columns will not. Main features added here are ebook and cover image support, library configuration, two custom fields, and a table that could one day store user emails, if we need to store them (currently we do not). 
    conn = sqlite3.connect(DB_LOCATION)
    initData =["1.0.1",False,"","",",".join(schemas.DEFAULT_GENRES)]
    cursor = conn.execute('create table if not exists Config (id INTEGER PRIMARY KEY, version VARCHAR, coverImages BOOLEAN, customFieldName1 VARCHAR, customFieldName2 VARCHAR, genres VARCHAR);')
    cursor = conn.execute('create table if not exists ebooks (id INTEGER PRIMARY KEY, bookId INTEGER, filename VARCHAR);')
    cursor = conn.execute('create table if not exists userEmails (id INTEGER PRIMARY KEY, email VARCHAR, userId INTEGER);')
    cursor = conn.execute('INSERT INTO config (version, coverImages, customFieldName1, customFieldName2, genres) VALUES (?, ?, ?, ?, ?);', initData)
    cursor = conn.execute('ALTER TABLE books DROP coverImage;')
    cursor = conn.execute('ALTER TABLE books ADD COLUMN withdrawnBy VARCHAR;')
    cursor = conn.execute('ALTER TABLE books ADD COLUMN ebook BOOLEAN;')
    cursor = conn.execute('ALTER TABLE books ADD COLUMN customField1 VARCHAR;')
    cursor = conn.execute('ALTER TABLE books ADD COLUMN customField2 VARCHAR;')
    conn.commit()
    conn.close()
    return

def updateDBVersion(db: Session, version):
    if version == "1.0.0":
        conn = sqlite3.connect(DB_LOCATION)
        #Version 1.0.0->1.0.1: We add a genres field to config, which contains the default list of genres, so users can change it. Previously it was hardcoded. 
        cursor = conn.execute('ALTER TABLE config ADD COLUMN genres VARCHAR;')
        cursor = conn.execute('UPDATE config SET genres = ? where id = 1;',(",".join(schemas.DEFAULT_GENRES),))
        cursor = conn.execute('UPDATE config SET version = ? where id = 1;',("1.0.1",))
        conn.commit()
        conn.close()
    return

 
        
def getConfig(db: Session):
    try:
        config = db.query(models.config).first()
        return config
    except Exception as e:
        print(e)
        return

def getVersion():
    try:
        conn = sqlite3.connect(DB_LOCATION)
        cur = conn.cursor()
        version = cur.execute("SELECT version FROM config")
        version = version.fetchone()[0]
        conn.close()
        return version
    except Exception as e:
        print(e)
        return

def updateConfig(db: Session, config: schemas.config):
    try:
        config_exists = db.query(models.config).first()
        config = models.config(** config.model_dump())
        if config_exists:
            db.merge(config)
            db.commit()
        else:
            db.add(config)
            db.commit()
            db.refresh(config) 
    except Exception as e:
        print(e)
        return  
        
def initConfig(db: Session):
    try:
        config = db.query(models.config).first()
        if not config:    
            conn = sqlite3.connect(DB_LOCATION)
            initData =["1.0.1",False,"","",",".join(schemas.DEFAULT_GENRES), False, False]
            cursor = conn.execute('create table if not exists Config (id INTEGER PRIMARY KEY, version VARCHAR, coverImages BOOLEAN, customFieldName1 VARCHAR, customFieldName2 VARCHAR, genres VARCHAR, patronSelfService BOOLEAN, ebooksEnabled BOOLEAN);')
            cursor = conn.execute('INSERT INTO config (version, coverImages, customFieldName1, customFieldName2, genres, patronSelfService, ebooksEnabled) VALUES (?, ?, ?, ?, ?, ?, ?);', initData)
            conn.commit()
            conn.close()
            ensure_schema()
            return
        else:
            return
    except Exception as e:
        print(e)
        return
    
def getImages(db: Session, bookId: int):
    try:
        limit = 16
        return db.query(models.bookImage).filter(models.bookImage.bookId == bookId).limit(limit).all()  
    except Exception as e:
        print(e)
        return 
        
def getImagesByFilename(db: Session, filename: str):
    try:
        image = db.query(models.bookImage).filter(models.bookImage.filename == filename).first()
        if image:
            return True
        if not image:
            return False
    except Exception as e:
        print(e)
        return False

def addImage(db: Session, image: schemas.bookImageBase):
    try:
        image = models.bookImage(** image.model_dump())
        db.add(image)
        db.commit()
        db.refresh(image)
        return "True"
    except Exception as e:
        print(e)
        return "False"
 
    
def deleteImage(db: Session, imageId: int):
    try:
        image = db.query(models.bookImage).filter(models.bookImage.id == imageId).first()
        bookId = image.bookId
        dbpath = image.filename
        db.delete(image)
        db.commit()
        return bookId,dbpath
    except Exception as e:
        print(e)
        return "False"

def addEbook(db: Session, ebook: schemas.ebookBase):
    try:
        ebook = models.ebook(** ebook.model_dump())
        db.add(ebook)
        db.commit()
        db.refresh(ebook)
        return "True"
    except Exception as e:
        print(e)
        return "False"
 
    
def deleteEbook(db: Session, ebookId: int):
    try:
        ebook = db.query(models.ebook).filter(models.ebook.id == ebookId).first()
        bookId = ebook.bookId
        dbpath = ebook.filename
        db.delete(ebook)
        db.commit()
        return bookId,dbpath
    except Exception as e:
        print(e)
        return "False"
        
def getEbookFiles(db: Session, bookId: int):
   try:
        limit = 32
        return db.query(models.ebook).filter(models.ebook.bookId == bookId).limit(limit).all()  
   except Exception as e:
        print(e)
        return        

def newUserLink(db: Session):
    try:
        unique_id = str(uuid.uuid4())
        newUserLink = models.link(accessCode=unique_id)
        db.add(newUserLink)
        db.commit()
        db.refresh(newUserLink)
        return unique_id
    except: return False        
    
def codeValidate(db: Session, accessCode: str):
    try:
        exists = db.query(models.link).filter(models.link.accessCode == accessCode).first()
        #timestamp depends on the DB, which ought to be UTC. It must be at most 3 days old.
        lastValid = datetime.utcnow() - timedelta(days = 3)
        if (exists is not None) and (exists.validity >= lastValid):
            #Link exists and is valid
            return True
        elif (exists is not None) and (exists.validity < lastValid):
            #Link exists, but is not valid
            db.delete(exists)
            db.commit()
            return False
        else:
            return False           
    except Exception as e: 
        print(e)
        return False 
        
def createWithCode(db: Session, user: schemas.UserCreate, accessCode: str):
    try:
        exists = db.query(models.link).filter(models.link.accessCode == accessCode).first()
        #timestamp depends on the DB, which ought to be UTC. It must be at most 3 days old.
        lastValid = datetime.utcnow() - timedelta(days = 3)
        if (exists is not None) and (exists.validity >= lastValid):
            #Link exists and is valid, void the link and create the user
            db.delete(exists)
            db.commit()
            passhash = crypto.hash(str(user.password))
            db_user = models.User(username=user.username, passhash=passhash, isAdmin = user.isAdmin)
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
            return True
        elif (exists is not None) and (exists.validity < lastValid):
            #Link exists, but is not valid, delete the 
            db.delete(exists)
            db.commit()
            return False
        else:
            return False           
    except Exception as e: 
        return False 
        
def searchUsers(db: Session, name: str):
    try:
        term = f"%{name}%"
        return db.query(models.User).filter(or_(
            models.User.username.ilike(term),
            models.User.givenName.ilike(term),
            models.User.surname1.ilike(term),
            models.User.surname2.ilike(term),
            models.User.phone.ilike(term),
            models.User.email.ilike(term),
            models.User.canton.ilike(term),
            models.User.district.ilike(term),
        )).all()
    except:
        return False

def promoteUser(db: Session, userId: int):
    try:
        user = db.query(models.User).filter(models.User.id == userId).first()
        user.isAdmin = True
        db.merge(user)
        db.commit()
        return True
    except:
        return False
def demoteUser(db: Session, userId: int):
    try:
        user = db.query(models.User).filter(models.User.id == userId).first()
        user.isAdmin = False
        db.merge(user)
        db.commit()
        return True
    except:
        return False

def deleteUser(db: Session, userId: int):
    try:
        user = db.query(models.User).filter(models.User.id == userId).first()
        db.delete(user)
        db.commit()
        return True
    except:
        return False  
        
def haveKey(db: Session, key: str):
    try:
        result = db.query(models.vkey).filter(models.vkey.vkey==key)
        assert db.query(result.exists()).scalar()
        return True
    except Exception as e:
        print(e)
        return False

def deleteVkey(db: Session, keyId: int):
    try:
        vkey = db.query(models.vkey).filter(models.vkey.id == keyId).first()
        db.delete(vkey)
        db.commit()
        return True
    except:
        return False 
        
def addVkey(db: Session, newKey: schemas.vkeyBase):
    try:
        vkey = models.vkey(** newKey.model_dump())
        db.add(vkey)
        db.commit()
        db.refresh(vkey)
        return True
    except Exception as e:
        print(e)
        return False
def getAllVkeys (db: Session):
    try:
        return db.query(models.vkey).all()
    except Exception as e:
        print(e)
        return
        
def getVkeyById(db: Session, keyId: int):
    try:
        result = db.query(models.vkey).filter(models.vkey.id==keyId).first()
        return result
    except Exception as e:
        print(e)
        return False
        
def updateVkey(db: Session, newKey: schemas.vkey):
    try:  
        oldVkey = db.query(models.vkey).filter(models.vkey.id == newKey.id).first()
        oldVkey.vkey = newKey.vkey
        db.merge(oldVkey)  
        db.commit()
    except Exception as e:
        print(e)
        return False


def stats(db: Session, isSum, group, target):
    if (isSum == True) and (len(group)) == 0: 
        results = db.query(getattr(models.Book, target), func.sum(getattr(models.Book, target))).all()
        return dict(results)
    elif (isSum == False) and (len(group)) == 0: 
        results = db.query(getattr(models.Book, target), func.count()).all()
        return dict(results)
    elif (isSum == True) and (len(group)) != 0:
        results = db.query(getattr(models.Book, group), func.sum(getattr(models.Book, target))).group_by(getattr(models.Book, group)).all()
        return dict(results)
    else:
        results = db.query(getattr(models.Book, target), func.count()).group_by(getattr(models.Book, group)).all()          
        return dict(results)
        
#def advancedSearch(db: Session, isSum, group, target):
#author,title,location, genre
#ebook / not ebook
#ISBN
#library, shelf
#2 custom fields
