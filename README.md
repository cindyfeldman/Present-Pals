HTTPS clone the repo to your local machine



Remember to always create your own local branch.
        1. git pull origin main (first pull all latest changes from main to your local)
        2. git checkout -b new-branch-name (create a new branch and checkout to it)
        3. git push --set-upstream origin new-branch-name 
        4. - - make your code changes - -
        5. git add file-you-want-to-commit
        6. git commit -m "add a message"
        7. git push
        8. Go to github and check that all your changes were tracked properlly. Create a Pull Request.
        9. If no objections, click Merge.  

        

Run the scripts in your terminal to build the index on you local code.
- python src/scripts/merge_data.py #This should create a folder called "data" with a "products_clean.json" file in it
- python src/scripts/build_index.py #This should create a folder called "index" with 4 files in it
These json files for the index are too big, so I cant push them on git, so you have to build it locally instead by running these scripts. 


    
Now that you have the information locally, you can run test querries
   - python src/scripts/query_tfidf.py --recipient mom --min_price 10 --max_price 80 --q "knife set"

