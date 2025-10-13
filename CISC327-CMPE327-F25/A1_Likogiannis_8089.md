Function Name | Implementation Status (Complete / Partial) | What is Missing?
--- | --- | --- 
Add Book To Catalog | Complete |
Book Catalog Display | Complete |
Book Borrowing Interface | Complete | 
Book Return Processing | Partial | Does not yet: verify the book was actually borrowed by the specific patron, update available copies count, record the return date, calculate and display and late fees owed
Late Fee Calculation API | Partial | Returns fee amount and days overdue, but does not calculate those values, only assumes those values are both 0
Book Search Functionality | Partial | Missing title search, author search, ISBN search, and return results for any search's besides view all books
Patron Status Report | Incomplete | Missing entire Patron Status Report Submenu