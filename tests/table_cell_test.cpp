#include "table.h"
#include <cassert>

std::vector<std::string> MESSAGES;

int main() {
  GLOBAL_instructor_output = true;
  assert(TableCell("ffffff", -7).make_cell_string(true) == "-7");
  assert(TableCell("ffffff", -2.5f, 1).make_cell_string(true) == "-2.5");

  TableCell contact("ffffff", "private-contact", "", 0, CELL_CONTENTS_VISIBLE_INSTRUCTOR);
  contact.LiteralCSV();
  GLOBAL_instructor_output = false;
  assert(contact.make_cell_string(true).empty());
  std::ostringstream html;
  html << contact;
  assert(html.str().find("private-contact") == std::string::npos);
  std::cout << "4 table-cell checks passed\n";
}
