#pragma once
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>
#ifdef _WIN32
#include <process.h>
#else
#include <sys/wait.h>
#include <unistd.h>
#endif

#ifdef _WIN32
// MSVCRT spawn joins argv into a command line. Quote each argument using the
// Windows backslash/quote rules so paths and commit messages stay single args.
inline std::string windows_argument(const std::string& value) {
    std::string result = "\"";
    size_t slashes = 0;
    for (char c : value) {
        if (c == '\\') { ++slashes; continue; }
        result.append(c == '"' ? slashes * 2 + 1 : slashes, '\\');
        result += c;
        slashes = 0;
    }
    result.append(slashes * 2, '\\');
    return result + "\"";
}
#endif

// Pass argv directly to Python. No shell, password arguments, or shared temp files.
inline int launch(int argc, char* argv[]) {
    namespace fs = std::filesystem;
    fs::path script = fs::absolute(argv[0]).parent_path().parent_path() / "load.py";
    if (!fs::exists(script)) {
        std::cerr << "Cannot locate load.py. Run the executable from build/.\n";
        return 1;
    }
    const char* configured = std::getenv("KITSUMA_PYTHON");
    std::vector<std::string> values{configured ? configured : "python", script.string()};
    for (int i = 1; i < argc; ++i) values.emplace_back(argv[i]);
    std::vector<char*> args;
#ifdef _WIN32
    std::vector<std::string> quoted;
    for (const auto& value : values) quoted.push_back(windows_argument(value));
    for (auto& value : quoted) args.push_back(value.data());
#else
    for (auto& value : values) args.push_back(value.data());
#endif
    args.push_back(nullptr);
#ifdef _WIN32
    auto result = _spawnvp(_P_WAIT, values[0].c_str(), args.data());
    if (result != -1) return static_cast<int>(result);
#else
    auto pid = fork();
    if (pid == 0) { execvp(args[0], args.data()); _exit(127); }
    int result = 0;
    if (pid > 0 && waitpid(pid, &result, 0) != -1 && WIFEXITED(result)) return WEXITSTATUS(result);
#endif
    std::cerr << "Could not start Python. Set KITSUMA_PYTHON to your Python executable.\n";
    return 1;
}
