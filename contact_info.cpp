#include "contact_info.h"

#include <arpa/inet.h>
#include <algorithm>
#include <cctype>

namespace {

bool ascii_alphanumeric(unsigned char c) {
  return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
}

std::string escape_html(const std::string &value) {
  std::string result;
  for (char c : value) {
    switch (c) {
      case '&': result += "&amp;"; break;
      case '<': result += "&lt;"; break;
      case '>': result += "&gt;"; break;
      case '"': result += "&quot;"; break;
      case '\'': result += "&#39;"; break;
      default: result += c;
    }
  }
  return result;
}

std::string encode_path_component(const std::string &value) {
  const char *hex = "0123456789ABCDEF";
  std::string result;
  for (unsigned char c : value) {
    if (ascii_alphanumeric(c) || c == '-' || c == '_' || c == '.' || c == '~') result += c;
    else {
      result += '%';
      result += hex[c >> 4];
      result += hex[c & 15];
    }
  }
  return result;
}

bool valid_username(const std::string &value, ContactField field) {
  const bool github = field == CONTACT_GITHUB;
  if (value.size() < (github ? 1u : 3u) || value.size() > (github ? 39u : 100u)) return false;
  if (!ascii_alphanumeric(value.front()) || !ascii_alphanumeric(value.back())) return false;
  char previous = 0;
  for (unsigned char c : value) {
    if (!ascii_alphanumeric(c) && c != '-') return false;
    if (github && c == '-' && previous == '-') return false;
    previous = c;
  }
  return true;
}

bool valid_port(const std::string &port) {
  if (port.empty() || port.size() > 5) return false;
  unsigned int number = 0;
  for (char c : port) {
    if (c < '0' || c > '9') return false;
    number = number * 10 + (c - '0');
  }
  return number <= 65535;
}

bool valid_host(std::string host) {
  if (!host.empty() && host.back() == '.') host.pop_back();
  if (host.empty() || host.back() == '.' || host.size() > 253) return false;
  std::size_t start = 0;
  while (start < host.size()) {
    std::size_t end = host.find('.', start);
    if (end == std::string::npos) end = host.size();
    if (end == start || end - start > 63 || !ascii_alphanumeric(host[start]) || !ascii_alphanumeric(host[end - 1])) return false;
    for (std::size_t i = start; i < end; i++) {
      if (!ascii_alphanumeric(host[i]) && host[i] != '-') return false;
    }
    start = end + 1;
  }
  return true;
}

bool valid_webpage(const std::string &value) {
  if (value.empty() || value.size() > 2048) return false;
  for (std::size_t i = 0; i < value.size(); i++) {
    unsigned char c = value[i];
    if (c <= 0x20 || c == 0x7f || c == '<' || c == '>' || c == '"' || c == '\'' || c == '\\') return false;
    if (c == '%') {
      if (i + 2 >= value.size() || !std::isxdigit(static_cast<unsigned char>(value[i + 1])) || !std::isxdigit(static_cast<unsigned char>(value[i + 2]))) return false;
      i += 2;
    }
  }
  std::size_t scheme_end = value.find("://");
  if (scheme_end == std::string::npos) return false;
  std::string scheme = value.substr(0, scheme_end);
  std::transform(scheme.begin(), scheme.end(), scheme.begin(), [](unsigned char c) { return std::tolower(c); });
  if (scheme != "http" && scheme != "https") return false;
  std::size_t start = scheme_end + 3;
  std::string authority = value.substr(start, value.find_first_of("/?#", start) - start);
  if (authority.empty() || authority.find('@') != std::string::npos) return false;
  if (authority.front() == '[') {
    std::size_t end = authority.find(']');
    if (end == std::string::npos) return false;
    unsigned char address[16];
    // inet_pton parses a literal address locally; it performs no DNS/network request.
    if (inet_pton(AF_INET6, authority.substr(1, end - 1).c_str(), address) != 1) return false;
    return end + 1 == authority.size() || (authority[end + 1] == ':' && valid_port(authority.substr(end + 2)));
  }
  std::size_t colon = authority.find(':');
  if (colon != std::string::npos && !valid_port(authority.substr(colon + 1))) return false;
  return valid_host(authority.substr(0, colon));
}

} // namespace

std::string ContactInfoHTML(const std::string &value, ContactField field) {
  std::string href;
  if (field == CONTACT_WEBPAGE) {
    if (valid_webpage(value)) href = value;
  } else if (valid_username(value, field)) {
    href = (field == CONTACT_LINKEDIN ? "https://www.linkedin.com/in/" : "https://github.com/") + encode_path_component(value);
  }
  const std::string text = escape_html(value);
  if (href.empty()) return text;
  return "<a href=\"" + escape_html(href) + "\" target=\"_blank\" rel=\"noopener noreferrer\">" + text + "</a>";
}
