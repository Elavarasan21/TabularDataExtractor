from flask import Flask,render_template,request,send_file,send_from_directory
import camelot
import pandas as pd
import xlsxwriter
import re
import numpy
import cv2
import datetime
from PyPDF2 import PdfFileMerger,PdfFileReader,PdfFileWriter
import os

current_directory=os.path.abspath(os.getcwd())

'''
PATHS
-----  '''

uploaded_pdfs_folder = os.path.join(current_directory,"uploaded_pdfs")
merged_pdf_location= os.path.join(current_directory,"tempdf.pdf")
extracted_spreadsheet_location = os.path.join(current_directory,"result.xlsx")
table_images_folder=os.path.join(current_directory,"table_images")

flask_app_template_folder=current_directory
template_file="pdf_table_extraction_web_page.html"

if not os.path.exists(uploaded_pdfs_folder):
    os.makedirs(uploaded_pdfs_folder)
if not os.path.exists(table_images_folder):
    os.makedirs(table_images_folder)

'''
GLOBAL VARIABLES
------ ---------  '''
                  
tables=None
table_images=None
file_names=None
saved_location_of_main_pdf=None
uploaded_files=None
uploaded_filenames_list=None
page_numbers_string=None
isUploaded=False
isExtracted=False
isDisplayed=False
mainPdfPgNos_to_pdfs_dict=None
pdf_names_of_table=None
pg_nos_of_table=None
uploaded_filenames_list=None

'''
HELPER FUNCTIONS
------ ---------  '''
def filterEmptyTables(tables_as_lists,images,page_numbers):
    filtered_tables=[]
    filtered_images=[]
    filtered_page_numbers=[]
    for table,image,page_number in zip(tables_as_lists,images,page_numbers):
        table_striped=[[col.strip().replace("\n"," ").replace("|"," ") for col in row] for row in table]
        flag=any([any(row) for row in table_striped])
        if flag :
            filtered_tables.append(table_striped)
            filtered_images.append(image)
            filtered_page_numbers.append(page_number)
    return filtered_tables,filtered_images,filtered_page_numbers

def generate_pdfNames_and_pgNos_of_tables(page_numbers):
    global mainPdfPgNos_to_pdfs_dict
    
    pdf_names_of_table=[]
    pg_nos_of_table=[]
    
    for p in page_numbers:
        for start,end in mainPdfPgNos_to_pdfs_dict.keys():
            if p>=start and p<=end :
                pdf_name=mainPdfPgNos_to_pdfs_dict[(start,end)][0]
                page_indx=p-start
                page_num=mainPdfPgNos_to_pdfs_dict[(start,end)][1][page_indx]
                
                pdf_names_of_table.append(pdf_name)
                pg_nos_of_table.append(page_num)

    return pdf_names_of_table,pg_nos_of_table

def extract_table(saved_pdf_location):
    '''
    Extract Tables from PDF file using camelot library.

    Parameters : saved_pdf_location - (str) location of PDF file.
    
    Returns    : tables_as_lists - (list) list of extracted tables(as list of lists).
                 table_images    - (list) list of original table images.                    '''
    
    file=saved_pdf_location
    tables,table_images,page_numbers=camelot.read_pdf(file,pages='all')
    tables_as_lists=[table.df.values.tolist() for table in tables]
    tables_as_lists,table_images,page_numbers=filterEmptyTables(tables_as_lists,table_images,page_numbers)

    pdf_names_of_table,pg_nos_of_table=generate_pdfNames_and_pgNos_of_tables(page_numbers)
    
    return tables_as_lists,table_images,pdf_names_of_table,pg_nos_of_table


def save_tables_as_spreadsheet(tables_as_lists):
    '''
    Converts tables of the form list of lists in to spread sheet form and saves the same.

    Parameters : tables_as_lists - (list) list of tables(as list of lists).
    
    Returns    : extracted_spreadsheet_location - (str) path of the location where tables in spread sheet form is stored.  '''
                                                                                                          
    
    global extracted_spreadsheet_location
    
    rows_count=list(map(lambda lis:len(lis),tables_as_lists))
    tables=[pd.DataFrame(table) for table in tables_as_lists]
    writer = pd.ExcelWriter(extracted_spreadsheet_location,engine='xlsxwriter',mode='w')   
    workbook=writer.book
    worksheet=workbook.add_worksheet('sheet_1')
    writer.sheets['sheet_1'] = worksheet
    start_row=0
    for table,no_of_rows in zip(tables,rows_count):
        table.to_excel(writer,sheet_name='sheet_1',startrow=start_row , startcol=0,header=False, index=False)
        start_row+=no_of_rows+2
    writer.save()
    return extracted_spreadsheet_location


def change_values(html_form,tables):
    '''
    Stores the modifications made on the tables while displaying them.

    Parameters : html_form - (dict) html form which contains contents of the modified table as <input> elements.
                 tables    - (list) list of tables(as list of lists).
                 
    Returns    : tables - (list) list of modified tables(as list of lists).                                       '''
                                                                                                                
    
    for key in html_form.keys():
        if re.search("^\d{1,}-\d{1,}-\d{1,}$",key):
            t,r,c=map(int,key.split("-"))
            tables[t][r][c]=html_form[key]
    return tables


def save_table_images(dir_path,table_images):
    '''
    Stores the table images in specified directory.

    Parameters : dir_path     - (str) path of the directory in which table images are to be stored.
                 table_images - (list) list of original table images.
                 
    Returns    : file_names - (list) list of file names of the stored images.                        '''
                                                                                                    

    file_names=[]
    for i,img in enumerate(table_images):
        file_name=datetime.datetime.now().strftime("%y%m%d%H%M%S")+str(i)+".jpg"
        full_path=dir_path+"/{}".format(file_name)
        file_names.append(file_name)
        isSaved=cv2.imwrite(full_path,img)
    return file_names

def getAllPageNumbers(pgs,total_pages):
	if 'all' in pgs:
		return list(range(0,total_pages))
	page_nos=set()
	pgs_splitted=list(map(lambda s:s.strip(),pgs.split(",")))
	for i in pgs_splitted:
		if i.isdigit():
			page_nos.add(int(i)-1)
		elif '-' in i:
			l,r=i.split('-')
			l=0 if l=='' else int(l)-1
			r=total_pages if r=='' else int(r)
			page_nos.update(range(l,r))
	return(sorted(list(page_nos)))
    
def getPdfNoPageNo(page_numbers_string):
    global uploaded_filenames_list
    if page_numbers_string.strip():
        pdfs=page_numbers_string.split(';')
        pdf_names_and_pages=[]
        for pdf in pdfs:
            pdf_no,pgs=pdf.split(':')
            pdf_names_and_pages.append((uploaded_filenames_list[int(pdf_no)-1],pgs))
        pdf_names_and_pages=dict(pdf_names_and_pages)
        return pdf_names_and_pages
    else:
        return dict()


def store_and_merge_uploaded_files(files_list,page_numbers_string):
    '''
    Stores multiple uploaded PDF files and merge them into a single PDF file.

    Parameters : files_list - (list) list of pdf files in request.file format.
    
    Returns    : merged_pdf_location - (str) path of location where the merged pdf stored.      '''
                                                                                             

    global uploaded_pdfs_folder
    global uploaded_filenames_list
    global mainPdfPgNos_to_pdfs_dict
    global merged_pdf_location
    

    pdf_paths=[]
    for pdf_file in files_list:
        pdf_path=uploaded_pdfs_folder+pdf_file.filename
        pdf_file.save(pdf_path)
        pdf_paths.append(pdf_path)
        
    
    mainPdfPgNos_to_pdfs_dict=dict()
    
    pdfNo_PgNos=getPdfNoPageNo(page_numbers_string)
    writer=PdfFileWriter()
    total_no_pages_in_main_pdf=0
    for i in range(len(pdf_paths)):
        pdf_path=pdf_paths[i]
        
        file_name=uploaded_filenames_list[i]
        
        pdf_page_no_string=pdfNo_PgNos.get(file_name,"all")
        pdfReader=PdfFileReader(pdf_path)
        total_pages=pdfReader.getNumPages()
        page_no_list=getAllPageNumbers(pdf_page_no_string,total_pages)
        for j in page_no_list:
            writer.addPage(pdfReader.getPage(j))
            
        start=total_no_pages_in_main_pdf+1
        end=total_no_pages_in_main_pdf+len(page_no_list)
        total_no_pages_in_main_pdf+=len(page_no_list)
        
        mainPdfPgNos_to_pdfs_dict[(start,end)]=(file_name,page_no_list)
        
                   
    merged_pdf_handler=open(merged_pdf_location,'wb')
    writer.write(merged_pdf_handler)
    merged_pdf_handler.close()
    return merged_pdf_location


'''
FLASK APP CODES
----- --- -----  '''
                 
app = Flask(__name__,template_folder=flask_app_template_folder)


@app.route("/")
def home():
    return render_template(template_file)


@app.route('/upload_file', methods=['GET', 'POST'])
def upload_file():
    #get the file by its id from the submitted form request
    files_list =request.files.getlist("pdfile")
    if files_list:
        global saved_location_of_main_pdf
        global uploaded_files
        global uploaded_filenames_list
        global page_numbers_string
        global isUploaded
        global template_file
        global uploaded_filenames_list
        
        uploaded_filenames_list=[f.filename for f in files_list]
        uploaded_files=" , ".join(uploaded_filenames_list)
        page_numbers_string=request.form['page_no']
        saved_location_of_main_pdf=store_and_merge_uploaded_files(files_list,page_numbers_string)
        isUploaded=True
    return render_template(
        template_file,
        #uploaded_file_names=uploaded_files if uploaded_files else "",
        page_numbers=page_numbers_string if page_numbers_string else "",
        isUploaded=isUploaded,
        uploaded_pdf_names=uploaded_filenames_list
        )


@app.route('/extract')
def extract_tables():
    global tables
    global table_images
    global uploaded_files
    global saved_location_of_main_pdf
    global page_numbers_string
    global isExtracted
    global pdf_names_of_table
    global pg_nos_of_table
    global template_file
    global uploaded_filenames_list
    
    isExtracted=True
    tables,table_images,pdf_names,pg_nos=extract_table(saved_location_of_main_pdf)
    
    pdf_names_of_table=pdf_names
    pg_nos_of_table=pg_nos
    
    return render_template(
        template_file,
        page_numbers=page_numbers_string if page_numbers_string else "",
        isUploaded=isUploaded,
        isExtracted=isExtracted,
        uploaded_pdf_names=uploaded_filenames_list
        )


@app.route('/display')
def displayTables():
    global tables
    global table_images
    global file_names
    global page_numbers_string
    global isDisplayed
    global pdf_names_of_table
    global pg_nos_of_table
    global template_file
    global uploaded_filenames_list
    global table_images_folder
    
    dir_path=table_images_folder
    file_names=save_table_images(dir_path,table_images)
    isDisplayed=True
    return render_template(
        template_file,
        tables=tables,
        file_names=file_names,
        contain_tables=bool(tables),
        msg="Extracted Tables" if bool(tables) else "No Tables Found",
        page_numbers=page_numbers_string if page_numbers_string else "",
        isUploaded=isUploaded,
        isExtracted=isExtracted,
        isDisplayed=isDisplayed,
        pdf_names=pdf_names_of_table,
        pg_nos=pg_nos_of_table,
        uploaded_pdf_names=uploaded_filenames_list
        )


@app.route('/download',methods=['GET', 'POST'])
def downloadFile():
    html_form=request.form
    global tables
    tables_changed=change_values(html_form,tables)
    
    table_no=html_form['table_no']
    if table_no=="all" :
        download_mask=html_form["download_mask"]
        filtered_tables=[tables_changed[i] for i in range(len(tables)) if int(download_mask[i])]            
        saved_path=save_tables_as_spreadsheet(filtered_tables)
    elif table_no.isnumeric() :
        table_inside_list=[tables_changed[int(table_no)]]
        saved_path=save_tables_as_spreadsheet(table_inside_list)
    #Returns the file mentioned in the path as attachment to the client
    return send_file(saved_path, as_attachment=True)

@app.route('/send_img/<file_name>')
def send_image(file_name):
    global table_images_folder
    return send_from_directory(table_images_folder,file_name)


    


if __name__ == "__main__":
    app.run(debug=True)
