from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, event
from sqlalchemy.orm import relationship
from sqlalchemy.orm.attributes import set_committed_value
from .database import Base
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    passhash = Column(String)
    isAdmin = Column(Boolean, default=False)
    givenName = Column(String, nullable=True)
    surname1 = Column(String, nullable=True)
    surname2 = Column(String, nullable=True)
    province = Column(String, nullable=True)
    canton = Column(String, nullable=True)
    district = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)

    @property
    def displayName(self):
        parts = [self.givenName, self.surname1, self.surname2]
        name = " ".join(part for part in parts if part)
        return name or self.username


from .field_crypto import ENCRYPTED_USER_FIELDS, decrypt_value, encrypt_value, is_ciphertext


@event.listens_for(User, "load")
def _decrypt_user_pii(target, context):
    for name in ENCRYPTED_USER_FIELDS:
        value = getattr(target, name)
        if is_ciphertext(value):
            set_committed_value(target, name, decrypt_value(value))


@event.listens_for(User, "before_insert")
@event.listens_for(User, "before_update")
def _encrypt_user_pii(mapper, connection, target):
    for name in ENCRYPTED_USER_FIELDS:
        value = getattr(target, name)
        if value and not is_ciphertext(value):
            setattr(target, name, encrypt_value(value))

class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    author = Column(String)
    summary = Column(String)
    genre = Column(String)
    library = Column(String)
    shelf = Column(String)
    collection = Column(String)
    ISBN = Column(String)
    notes = Column(String, nullable=True)
    owned = Column(Boolean)
    withdrawn = Column(Boolean)
    withdrawnBy = Column(String, nullable=True)
    customField1 = Column(String, nullable=True)
    customField2 = Column(String, nullable=True)
    ebook = Column(Boolean,nullable=True, default=False)
    publisher = Column(String, nullable=True)
    pages = Column(Integer, nullable=True)
    copies = Column(Integer, nullable=True, default=1)
    available = Column(Integer, nullable=True, default=1)

class Loan(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True)
    bookId = Column(Integer, ForeignKey("books.id"))
    username = Column(String, nullable=False)
    active = Column(Boolean, default=True)

class readingListItems(Base):
    __tablename__ = "readinglistitems"
    id = Column(Integer, primary_key=True)
    book = Column(Integer, ForeignKey("books.id"))
    user_id = Column(Integer)
    
class bookImage(Base):
    __tablename__ = "bookImages"
    id = Column(Integer, primary_key=True)
    bookId = Column(Integer, ForeignKey("books.id"))
    filename = Column(String, nullable=False)  

class config(Base):
    __tablename__= "config"
    id = Column(Integer, primary_key=True)
    version = Column(String)
    coverImages = Column(Boolean)
    customFieldName1 = Column(String, nullable=True)
    customFieldName2 = Column(String, nullable=True)
    genres = Column(String)
    patronSelfService = Column(Boolean, default=False)
    ebooksEnabled = Column(Boolean, default=False)
    theme = Column(String, nullable=True, default="light")

class ebook(Base):
    __tablename__ = "ebooks"
    id = Column(Integer, primary_key=True)
    bookId = Column(Integer, ForeignKey("books.id"))
    filename = Column(String, nullable=False) 

class emails(Base):
    __tablename__ = "userEmails"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=True)
    user_id = Column(Integer)
    
class link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True)
    accessCode = Column(String, index=True)
    validity = Column(DateTime(timezone=True), server_default=func.now())
    
class vkey(Base):
    __tablename__ = "vkeys"
    id = Column(Integer, primary_key=True)
    vkey = Column(String, index=True)
    url = Column(String, index=True)
    
    
