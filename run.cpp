#include <bits/stdc++.h>
#include <fstream>
using namespace std;

int main(){
    system("cls");
    cout << "WELCOME TO KITSUMA - HIERARCHY BASED VERSION CONTROL SYSTEM\n";
    bool chosen = false;
    string user; 
    while (!chosen) {
        char choice;
        cout << "Do you want to Signup(S) or Login(L): ";
        cin >> choice;
        if (choice == 's' || choice == 'S') {
            chosen = true;
            while (true) {
                string sign_up, new_pass;
                cout << "Enter your AdminID: ";
                cin >> sign_up;
                cout << "Enter your AdminPass: ";
                cin >> new_pass;
                string command = "python load.py S \"" + sign_up + "\" \"" + new_pass + "\"";
                int res = system(command.c_str());
                if (res == 0) {
                    cout << "Signup successful!\n";
                    user = sign_up;
                    break;
                }
                else if (res == 1) {
                    cout << "AdminID already exists. Try again.\n";
                }
                else {
                    cout << "Error occurred. Try again.\n";
                }
            }
        }
        else if (choice == 'l' || choice == 'L') {
            chosen = true;
            bool exists = false;
            while (true) {
                string login_id, password;
                cout << "Enter your LoginID: ";
                cin >> login_id;
                cout << "Enter your Password: ";
                cin >> password;
                string command = "python load.py L \"" + login_id + "\" \"" + password + "\"";
                int res = system(command.c_str());
                if (res == 0) {
                    exists = true;
                    cout << "\nWelcome to KITSUMA, " << login_id << endl;
                    user = login_id; 
                    break;
                }
                else if (res == 1) {
                    exists = false;
                    cout << "Invalid LoginID or Password. Try again.\n";
                }
                else {
                    exists = false;
                    cout << "Error occurred. Try again.\n";
                }
            }
        }
        else {
            cout << "Invalid option chosen. Try again.\n";
        }
    }
    string command = "python load.py G \"" + user + "\"";
    int res = system(command.c_str());
    return 0;
}

