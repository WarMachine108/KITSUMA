#include <bits/stdc++.h>
#include <cstdlib>
#include <filesystem>
using namespace std; 

int main(){
    vector <string> files;
    string currdir = filesystem::current_path().string(); 
    for (auto it = filesystem::recursive_directory_iterator("."); 
        it != filesystem::recursive_directory_iterator(); ++it) {
        string name = it->path().filename().string();
        if (name[0] == '.') {
            if (it->is_directory())
                it.disable_recursion_pending();
            continue;
        }
        string exclude = ".exe"; 
        int res = name.find(exclude); 
        if (res == string::npos){ 
            files.push_back(it->path().filename().string());
        }
    }
    cout << "All files present in current working directory: \n\n";
    for (int i=0; i<files.size(); i++){
        cout << files[i] << "\n"; 
    }
    cout << "\n";
    string n; 
    cout << "Enter number of files to add (. for all): ";
    cin >> n;
    if (n == "."){ 
        for (int i=0; i<files.size(); i++){ 
            string filename = files[i];
            ifstream file(filename); 
            string filecontent; 
            if (!file.is_open()){ 
                cout << "Failed to open file. "; 
                filecontent = "";  
            } 
            else{
                stringstream buffer; 
                buffer << file.rdbuf(); 
                filecontent = buffer.str(); 
                file.close(); 
            }
            ofstream temp("tempcontent.txt");
            temp << filecontent;
            temp.close();
            string command = "python load.py A \"" + filename + "\" tempcontent.txt";
            system(command.c_str());
        }
    }
    else{
        string filename;
        int num = stoi(n);
        while (num--){
            bool chosen = false;
            while (!chosen){ 
                cout << "Enter filename to add/update: "; 
                cin >> filename; 
                if (find(files.begin(), files.end(), filename) != files.end()) {
                    chosen = true; 
                } 
                else {
                    cout << "File does not exist in current working directory, Try again. \n"; 
                }
            }
            ifstream file(filename); 
            string filecontent; 
            if (!file.is_open()){ 
                cout << "Failed to open file. "; 
                filecontent = "";  
            } 
            else{
                stringstream buffer; 
                buffer << file.rdbuf(); 
                filecontent = buffer.str(); 
                file.close(); 
            }
            ofstream temp("tempcontent.txt");
            temp << filecontent;
            temp.close();
            string command = "python load.py A \"" + filename + "\" tempcontent.txt";
            system(command.c_str());
            if (filesystem::exists("tempcontent.txt")) {
                filesystem::remove("tempcontent.txt");
            }
        }
    }
    
    return 0; 
}