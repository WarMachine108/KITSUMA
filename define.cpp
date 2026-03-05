#include<iostream>
#include<cstdlib>
#include<fstream>
#include<string>
using namespace std;

class user{
private:
    string authority;
    string id;
public:
    user(string authority,string id){
        this->authority=authority;
        this->id=id;
    }
};

int main(){
    system("g++ run.cpp -o run && .\\run");
    user *u;
    string base="C:/testing";
    ifstream inputFile("structure.txt");
    if (!inputFile.is_open()) {
        std::cerr << "Error opening file: structure.txt" << std::endl;
        return 1;
    }
    bool auth=false,emps=false,structure=false,file=false,folder=true;
    string line,id,final="",file_name="";
    bool first=true;
    while(getline(inputFile,line)){
        if(first){
            id=line;
            first=false;
            continue;
        }
        if(line=="auth:"){
            auth=true;
            continue;
        }
        else if(line=="emps:"){
            auth=false;
            emps=true;
            continue;
        }
        else if(line=="struct:"){
            emps=false;
            structure=true;
            continue;
        }
        if(auth){
            u=new user(line,id);
        }
        if(emps){
        }
        if(structure){
            for(char i:line){
                file_name+=i;
                if(i=='/'){
                    file_name="";
                }
                if(i=='.'){
                    file=true;
                    folder=false;
                }
            }
            if(folder){
                final = "mkdir \"" + base + "/" + line + "\"";
                system(final.c_str());
            }
            if(file){
                final = "type nul > "+ base + "/" + line;
                system(final.c_str());
                final= "python load.py GF \"" + line + "\" \"" + base + "\" \"" + file_name + "\"";
                system(final.c_str());
                file=false;
                folder=true;
            }
        }
    }
    return 0;
}
