from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import crud, schemas
from ..database import SessionLocal
from ..dependencies import (
    get_rate_limiter, templates,
    current_user,
)

router = APIRouter()


@router.get("/read/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_read(bookId, request: Request, user: current_user):
    db = SessionLocal()
    try:
        readingListItem = schemas.readingListItemCreate(book=bookId, user_id=user.id)
        crud.readBook(db, readingListItem)
    finally:
        db.close()
    return RedirectResponse(url='/readingLists')


@router.get("/unread/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_unread(bookId, request: Request, user: current_user):
    db = SessionLocal()
    try:
        crud.bookUnRead(db, bookId)
    finally:
        db.close()
    return RedirectResponse(url='/readingLists')


@router.get("/readingLists", dependencies=[get_rate_limiter(times=2, seconds=2)], response_class=HTMLResponse)
async def reading_list(request: Request, user: current_user):
    db = SessionLocal()
    try:
        readingList = crud.readingList(db, user.id)
        books = [crud.getBookById(db, i.book) for i in readingList]
    finally:
        db.close()
    context = {
        "books": books,
        "user": user,
        "request": request,
    }
    return templates.TemplateResponse(request, "readinglist.html", context)


def _book_schema(book, withdrawn: bool, withdrawn_by: str | None = None) -> schemas.Book:
    copies, available = crud.stock_of(book)
    return schemas.Book(
        id=book.id, title=book.title, author=book.author, summary=book.summary,
        genre=book.genre, library=book.library, shelf=book.shelf, collection=book.collection,
        notes=book.notes, ISBN=book.ISBN, owned=book.owned, ebook=book.ebook,
        customField1=book.customField1, customField2=book.customField2,
        publisher=book.publisher, pages=book.pages, copies=copies, available=available,
        withdrawn=withdrawn, withdrawnBy=withdrawn_by,
    )


def _can_circulate(user, borrower: str | None = None) -> bool:
    if user.isAdmin:
        return True
    if not crud.patron_self_service_enabled():
        return False
    return borrower is None or borrower == user.username


@router.get("/return/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_return(bookId, request: Request, user: current_user):
    db = SessionLocal()
    try:
        book = crud.getBookById(db, bookId)
        loan = crud.active_loans(db, book.id)[0] if book else None
        if loan and _can_circulate(user, loan.username):
            crud.return_loan(db, loan)
        elif book and book.withdrawn and _can_circulate(user, book.withdrawnBy):
            copies, _available = crud.stock_of(book)
            book.available = min(copies, (book.available or 0) + 1)
            book.withdrawn = book.available == 0
            book.withdrawnBy = None
            db.commit()
    finally:
        db.close()
    return RedirectResponse(url='/withdrawn')


@router.get("/returnLoan/{loanId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def return_one_loan(loanId: int, request: Request, user: current_user):
    db = SessionLocal()
    try:
        loan = db.get(crud.models.Loan, loanId)
        if loan and _can_circulate(user, loan.username):
            crud.return_loan(db, loan)
    finally:
        db.close()
    return RedirectResponse(url='/withdrawn')


@router.get("/withdraw/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_withdraw_get(bookId, request: Request, user: current_user):
    return RedirectResponse(url=f'/bookDetails/{bookId}')


@router.post("/withdraw/{bookId}", dependencies=[get_rate_limiter(times=1, seconds=1)], response_class=HTMLResponse)
async def book_withdraw(bookId, request: Request, user: current_user, borrower: str = Form(...)):
    borrower = (borrower or "").strip()
    if not _can_circulate(user, borrower):
        return RedirectResponse(url=f'/bookDetails/{bookId}', status_code=status.HTTP_303_SEE_OTHER)
    db = SessionLocal()
    try:
        book = crud.getBookById(db, bookId)
        if not book:
            return RedirectResponse(url='/searchbooks', status_code=status.HTTP_303_SEE_OTHER)
        _copies, available = crud.stock_of(book)
        if available < 1:
            return RedirectResponse(url=f'/bookDetails/{bookId}', status_code=status.HTTP_303_SEE_OTHER)
        patron = crud.get_user_by_username(db, borrower)
        if not patron or patron.isAdmin:
            return RedirectResponse(url=f'/bookDetails/{bookId}', status_code=status.HTTP_303_SEE_OTHER)
        crud.lend_copy(db, book, patron.username)
    finally:
        db.close()
    return RedirectResponse(url='/withdrawn', status_code=status.HTTP_303_SEE_OTHER)


@router.get("/withdrawn", dependencies=[get_rate_limiter(times=2, seconds=2)], response_class=HTMLResponse)
async def withdrawn_list(request: Request, user: current_user):
    db = SessionLocal()
    try:
        loans = crud.active_loans(db)
        people = {person.username: person for person in crud.list_library_users(db)}
        rows = []
        for loan in loans:
            book = crud.getBookById(db, loan.bookId)
            if book:
                rows.append({"loan": loan, "book": book, "person": people.get(loan.username)})
    finally:
        db.close()
    counts = {}
    for row in rows:
        name = row["person"].displayName if row["person"] else row["loan"].username
        counts[name] = counts.get(name, 0) + 1
    summary = [{"name": name, "total": total} for name, total in sorted(counts.items(), key=lambda item: item[1], reverse=True)]
    context = {
        "user": user,
        "rows": rows,
        "summary": summary,
        "request": request,
    }
    return templates.TemplateResponse(request, "withdrawn.html", context)


@router.get("/wishlist", dependencies=[get_rate_limiter(times=2, seconds=2)], response_class=HTMLResponse)
async def wishlist(request: Request, user: current_user):
    db = SessionLocal()
    try:
        books = crud.browseWishlist(db)
    finally:
        db.close()
    context = {
        "user": user,
        "books": books,
        "request": request,
    }
    return templates.TemplateResponse(request, "wishlist.html", context)
