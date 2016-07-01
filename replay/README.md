# InsightAgent

InsightAgent support replay mode in which the data from the csv file is read and sent to insightfinder server.

# Steps to use replay mode:
1) Create a custom project on InsightFinder.com and get license key

2) Download the insightfinder agent code using this command, and untar insightagent.tar.gz in installation directory
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz

3) In InsightAgent-master directory, run the install command:
./install.sh -u INSIGHTFINDER_USER_NAME -k LICENSE_KEY -s 0 -r 0 -t replay

4) Put data files in InsightAgent-master/data/

5) For each data file, run the following command:
./reportMetrics.py -m replay -f PATH_TO_CSVFILENAME

PATH_TO_CSVFILENAME is the path and filename of the csv file.

