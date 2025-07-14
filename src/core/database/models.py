# Модели таблиц БД (SQLAlchemy/SQLModel)

from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Example model
# class Invoice(Base):
#     __tablename__ = 'invoices'
#     id = Column(Integer, primary_key=True)
