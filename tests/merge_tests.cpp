#define KITSUMA_NO_MAIN
#include "../update.cpp"
#include <random>

void check(bool condition, const string& description) {
    if (!condition) throw runtime_error(description);
}

vector<string> applyDiff(const vector<string>& base, const vector<Edit>& edits) {
    vector<string> output;
    size_t i=0;
    for (const auto& edit : edits) {
        if (edit.op != INS) {
            check(i<base.size() && base[i]==edit.s,"diff consumes correct source line");
            ++i;
        }
        if (edit.op != DEL) output.push_back(edit.s);
    }
    check(i==base.size(),"diff consumes all source lines");
    return output;
}

int main() {
    try {
        mt19937 random(42);
        for (int trial=0; trial<10000; ++trial) {
            vector<string> a,b;
            int n=random()%12, m=random()%12;
            for (int i=0;i<n;++i) a.push_back(to_string(random()%4)+"\n");
            for (int i=0;i<m;++i) b.push_back(to_string(random()%4)+"\n");
            check(applyDiff(a,myersDiff(a,b))==b,"diff round trip");
            auto regions=threeWayMerge(a,b,a);
            vector<string> merged;
            for (const auto& r:regions) {
                check(r.type!=CONFLICT,"one-sided edit is conflict-free");
                const auto& lines=r.type==ONLY_B ? r.b_lines : r.a_lines;
                merged.insert(merged.end(),lines.begin(),lines.end());
            }
            check(merged==b,"one-sided merge round trip");
            for (const auto& r:threeWayMerge(a,b,b)) check(r.type!=CONFLICT,"identical edits agree");
        }
        auto conflict=threeWayMerge({"old\n"},{},{"new\n"});
        check(conflict.size()==1 && conflict[0].type==CONFLICT,"delete-versus-edit conflicts");
        auto separate=threeWayMerge({"x\n","y\n"},{"X\n","y\n"},{"x\n","Y\n"});
        vector<string> output;
        for (const auto& r:separate) {
            check(r.type!=CONFLICT,"adjacent independent replacements merge");
            const auto& lines=r.type==ONLY_B ? r.b_lines : r.a_lines;
            output.insert(output.end(),lines.begin(),lines.end());
        }
        check(output==vector<string>({"X\n","Y\n"}),"independent replacements retained");
        cout << "Merge tests passed: 10,000 randomized diff/merge cases + conflict cases.\n";
        return 0;
    } catch (const exception& error) { cerr << error.what() << "\n"; return 1; }
}
