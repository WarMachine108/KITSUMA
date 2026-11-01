#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>
#include <stdexcept>
#include <filesystem>

using namespace std;

#define RESET   "\033[0m"
#define BOLD    "\033[1m"
#define DIM     "\033[2m"
#define RED     "\033[38;5;203m"
#define GREEN   "\033[38;5;114m"
#define YELLOW  "\033[38;5;221m"
#define BLUE    "\033[38;5;75m"
#define CYAN    "\033[38;5;87m"

enum Op { KEEP, INS, DEL };
struct Edit { Op op; string s; };

vector<Edit> myersDiff(const vector<string>& a, const vector<string>& b) {
    int N = (int)a.size(), M = (int)b.size(), MAX = N + M;
    if (N == 0 && M == 0) return {};
    if (N == 0) { vector<Edit> r; for (auto& l:b) r.push_back({INS,l}); return r; }
    if (M == 0) { vector<Edit> r; for (auto& l:a) r.push_back({DEL,l}); return r; }

    vector<int>         V(2*MAX+2, -1);
    vector<vector<int>> Vs;
    V[1+MAX] = 0;

    for (int D = 0; D <= MAX; D++) {
        Vs.push_back(V);
        for (int k = -D; k <= D; k += 2) {
            bool down = (k == -D || (k != D && V[k-1+MAX] < V[k+1+MAX]));
            int x = down ? V[k+1+MAX] : V[k-1+MAX] + 1;
            int y = x - k;
            while (x < N && y < M && a[x] == b[y]) { x++; y++; }
            V[k+MAX] = x;
            if (x == N && y == M) goto done;
        }
    }
done:
    vector<Edit> ops;
    int x = N, y = M;
    for (int D = (int)Vs.size()-1; D >= 0; D--) {
        auto& pV = Vs[D];
        int k    = x - y;
        bool down = (k == -D || (k != D && pV[k-1+MAX] < pV[k+1+MAX]));
        int pk   = down ? k+1 : k-1;
        int px   = pV[pk+MAX], py = px - pk;
        // diagonal snake going back
        while (x > px + (!down?1:0) && y > py + (down?1:0)) {
            ops.push_back({KEEP, a[x-1]}); x--; y--;
        }
        if (D == 0) break;
        if (down) { ops.push_back({INS, b[y-1]}); y--; }
        else      { ops.push_back({DEL, a[x-1]}); x--; }
    }
    reverse(ops.begin(), ops.end());
    return ops;
}

vector<string> readFile(const string& path) {
    ifstream f(path, ios::binary);
    if (!f) throw runtime_error("Cannot open input: " + path);
    vector<string> lines;
    string line;
    char c;
    while (f.get(c)) {
        line += c;
        if (c=='\n') { lines.push_back(line); line.clear(); }
    }
    if (f.bad()) throw runtime_error("Cannot read input: " + path);
    if (!line.empty()) lines.push_back(line);
    return lines;
}

bool writeFile(const string& path, const vector<string>& lines) {
    string temporary=path+".tmp";
    ofstream f(temporary,ios::binary | ios::trunc);
    if (!f) return false;
    for (const auto& line : lines) f << line;
    f.close();
    if (!f) return false;
    // The integration always uses a fresh output path in a private directory.
    // Refuse to overwrite an existing standalone output, preserving old results.
    if (filesystem::exists(path)) { filesystem::remove(temporary); return false; }
    error_code ec;
    filesystem::rename(temporary,path,ec);
    if (ec) { filesystem::remove(temporary); return false; }
    return true;
}

// A change replaces a half-open interval of base lines. Keeping replacements
// together lets delete-versus-edit become a conflict instead of two auto edits.
struct Change { int start, end; vector<string> lines; };
enum RegionType { UNCHANGED, ONLY_A, ONLY_B, CONFLICT };
struct MergeRegion { RegionType type; vector<string> base_lines, a_lines, b_lines; };

vector<Change> changesFromDiff(const vector<Edit>& diff) {
    vector<Change> result;
    int at = 0;
    bool active = false;
    Change current{0,0,{}};
    for (const auto& edit : diff) {
        if (edit.op == KEEP) {
            if (active) { result.push_back(current); active = false; }
            ++at;
        } else {
            if (!active) { current = {at,at,{}}; active = true; }
            if (edit.op == DEL) current.end = ++at;
            else current.lines.push_back(edit.s);
        }
    }
    if (active) result.push_back(current);
    return result;
}

vector<string> applyRegion(const vector<string>& base, int start, int end,
                           const vector<Change>& changes, size_t first, size_t last) {
    vector<string> result;
    int at = start;
    for (size_t i = first; i < last; ++i) {
        const auto& change = changes[i];
        result.insert(result.end(),base.begin()+at,base.begin()+change.start);
        result.insert(result.end(),change.lines.begin(),change.lines.end());
        at = change.end;
    }
    result.insert(result.end(),base.begin()+at,base.begin()+end);
    return result;
}

vector<MergeRegion> threeWayMerge(const vector<string>& base,
                                  const vector<string>& A, const vector<string>& B) {
    auto ca = changesFromDiff(myersDiff(base,A));
    auto cb = changesFromDiff(myersDiff(base,B));
    vector<MergeRegion> result;
    size_t ia=0, ib=0;
    int at=0;
    while (ia<ca.size() || ib<cb.size()) {
        int start = ia==ca.size() ? cb[ib].start : ib==cb.size() ? ca[ia].start : min(ca[ia].start,cb[ib].start);
        if (at<start) {
            vector<string> same(base.begin()+at,base.begin()+start);
            result.push_back({UNCHANGED,same,same,same});
        }
        int end=start;
        size_t fa=ia, fb=ib;
        // Include insertions at a replacement boundary conservatively. Adjacent
        // nonempty replacements remain separate and can merge independently.
        bool progress=true;
        while (progress) {
            progress=false;
            auto include = [&](const vector<Change>& c, size_t& i) {
                while (i<c.size() && (c[i].start==start || c[i].start<end ||
                       (c[i].start==end && c[i].start==c[i].end))) {
                    end=max(end,c[i].end); ++i; progress=true;
                }
            };
            include(ca,ia); include(cb,ib);
        }
        vector<string> original(base.begin()+start,base.begin()+end);
        auto av=applyRegion(base,start,end,ca,fa,ia);
        auto bv=applyRegion(base,start,end,cb,fb,ib);
        RegionType type = av==bv ? UNCHANGED : av==original ? ONLY_B : bv==original ? ONLY_A : CONFLICT;
        result.push_back({type,original,av,bv});
        at=end;
    }
    if (at<(int)base.size()) {
        vector<string> same(base.begin()+at,base.end());
        result.push_back({UNCHANGED,same,same,same});
    }
    return result;
}

void rule(const string& s, int n = 66) {
    for (int i = 0; i < n; i++) cout << s;
    cout << "\n";
}

string prompt(const string& msg) {
    string in;
    while (true) {
        cout << BOLD << YELLOW << "  > " << msg << " " << RESET;
        if (!getline(cin, in)) throw runtime_error("Input closed; merge cancelled.");
        if (!in.empty()) return in;
    }
}

vector<string> resolveConflict(const vector<string>& a,
                                const vector<string>& b, int n) {
    cout << "\n";
    rule("~");
    cout << BOLD << YELLOW << "  CONFLICT #" << n << RESET << "\n";
    rule("~");

    cout << "\n" << BOLD << "  Branch A (file1):\n" << RESET;
    if (a.empty()) cout << RED << DIM << "  (deleted)\n" << RESET;
    else for (auto& l : a) cout << RED   << "  - " << RESET << l << "\n";

    cout << "\n" << BOLD << "  Branch B (file2):\n" << RESET;
    if (b.empty()) cout << RED << DIM << "  (deleted)\n" << RESET;
    else for (auto& l : b) cout << GREEN << "  + " << RESET << l << "\n";

    cout << "\n"
         << "  [a]   keep A\n"
         << "  [b]   keep B\n"
         << "  [ab]  keep both (A then B)\n"
         << "  [ba]  keep both (B then A)\n"
         << "  [e]   enter custom text\n"
         << "  [s]   skip (drop both)\n\n";

    while (true) {
        string c = prompt("Choice:");
        if (c == "a")  return a;
        if (c == "b")  return b;
        if (c == "s")  return {};
        if (c == "ab") { auto r=a; r.insert(r.end(),b.begin(),b.end()); return r; }
        if (c == "ba") { auto r=b; r.insert(r.end(),a.begin(),a.end()); return r; }
        if (c == "e") {
            cout << "  Type lines, a single . to finish (blank lines are allowed):\n";
            vector<string> custom;
            string l;
            while (true) { cout << "  | "; if (!getline(cin,l)) throw runtime_error("Input closed; merge cancelled."); if(l==".") break; custom.push_back(l+"\n"); }
            return custom;
        }
        cout << RED << "  Unknown. Use: a / b / ab / ba / e / s\n" << RESET;
    }
}

vector<string> showAutoHunk(const MergeRegion& r, int n) {
    bool is_a = (r.type == ONLY_A);
    string branch = is_a ? "A (file1)" : "B (file2)";
    const auto& changed  = is_a ? r.a_lines : r.b_lines;
    const auto& original = r.base_lines;

    cout << "\n";
    rule("-");
    cout << BOLD << BLUE << "  AUTO-MERGE #" << n
         << RESET << DIM << "  only branch " << branch << " changed this\n" << RESET;
    rule("-");

    if (!original.empty()) {
        cout << DIM << "\n  base:\n" << RESET;
        for (auto& l : original) cout << DIM << "    " << l << RESET << "\n";
    }
    cout << "\n  result:\n";
    if (changed.empty()) cout << RED << DIM << "    (line deleted)\n" << RESET;
    else for (auto& l : changed) {
        bool is_new = find(original.begin(), original.end(), l) == original.end();
        if (is_new) cout << GREEN << "  + " << RESET << l << "\n";
        else        cout << DIM   << "    " << l << RESET << "\n";
    }

    cout << "\n  [y] accept   [n] override manually\n\n";
    while (true) {
        string c = prompt("Accept auto-merge?");
        if (c == "n") return resolveConflict(r.a_lines,r.b_lines,n);
        if (c == "y") return changed;
        cout << "Use y or n.\n";
    }
}

#ifndef KITSUMA_NO_MAIN
int main(int argc, char* argv[]) {
  try {
    if (argc != 5) throw runtime_error("Usage: update <base> <submitted> <current> <output>");
    string base_path = argv[1];
    string a_path    = argv[2];
    string b_path    = argv[3];
    string out_path  = argv[4];

    auto base = readFile(base_path);
    auto A    = readFile(a_path);
    auto B    = readFile(b_path);


    auto regions = threeWayMerge(base, A, B);

    int n_conflict = 0, n_auto = 0;
    for (auto& r : regions) {
        if      (r.type == CONFLICT)  n_conflict++;
        else if (r.type != UNCHANGED) n_auto++;
    }

    cout << "\n";
    rule("=");
    cout << BOLD << CYAN << "  3-WAY MERGE\n" << RESET;
    cout << DIM  << "  base: " << base_path
                 << "   A: " << a_path
                 << "   B: " << b_path << "\n" << RESET;
    rule("=");
    cout << "\n"
         << "  " << GREEN  << n_auto     << RESET << " auto-mergeable hunk(s)\n"
         << "  " << YELLOW << n_conflict << RESET << " conflict(s) to resolve\n\n";
    rule("-");
    cout << DIM << "  LEGEND:  " << RESET
         << GREEN  << "+ added  " << RESET
         << RED    << "- deleted  " << RESET
         << DIM    << "context unchanged\n" << RESET;
    rule("-");

    vector<string> output;
    int hunk_no = 0;

    for (auto& r : regions) {
        if (r.type == UNCHANGED) {
            for (auto& l : r.a_lines) output.push_back(l);
            continue;
        }
        hunk_no++;
        vector<string> resolved;
        if (r.type == CONFLICT) resolved = resolveConflict(r.a_lines, r.b_lines, hunk_no);
        else                    resolved = showAutoHunk(r, hunk_no);
        for (auto& l : resolved) output.push_back(l);
    }

    cout << "\n";
    rule("=");
    if (writeFile(out_path, output))
        cout << BOLD << GREEN  << "  Merge complete -> " << out_path << RESET << "\n";
    else throw runtime_error("Cannot write output (use a new output path): " + out_path);
    rule("=");
    cout << "\n";
    return 0;
  } catch (const exception& error) { cerr << "Error: " << error.what() << "\n"; return 1; }
}
#endif
