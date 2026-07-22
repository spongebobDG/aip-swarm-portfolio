#ifndef FRONTIER_SEARCH_H_
#define FRONTIER_SEARCH_H_

#include "nav2_costmap_2d/costmap_2d_ros.hpp"

namespace frontier_exploration
{
struct Frontier {
  std::uint32_t size;
  double min_distance;
  double cost;
  geometry_msgs::msg::Point initial;
  geometry_msgs::msg::Point centroid;
  geometry_msgs::msg::Point middle;
  std::vector<geometry_msgs::msg::Point> points;
};

class FrontierSearch
{
public:
  FrontierSearch() : logger_(rclcpp::get_logger("frontier_search")) {}

  FrontierSearch(nav2_costmap_2d::Costmap2D* costmap, double potential_scale,
                 double gain_scale, double min_frontier_size, rclcpp::Logger logger,
                 double goal_continuity_scale = 0.0);

  std::vector<Frontier> searchFrom(geometry_msgs::msg::Point position);

  // 이전 목표 좌표 설정 — goal_continuity_scale 항 계산에 사용
  void setGoalPosition(const geometry_msgs::msg::Point& goal) { prev_goal_ = goal; }

protected:
  Frontier buildNewFrontier(unsigned int initial_cell, unsigned int reference,
                            std::vector<bool>& frontier_flag);

  bool isNewFrontierCell(unsigned int idx,
                         const std::vector<bool>& frontier_flag);

  double frontierCost(const Frontier& frontier);

private:
  nav2_costmap_2d::Costmap2D* costmap_;
  unsigned char* map_;
  unsigned int size_x_, size_y_;
  double potential_scale_, gain_scale_;
  double goal_continuity_scale_;
  geometry_msgs::msg::Point prev_goal_;
  double min_frontier_size_;
  rclcpp::Logger logger_;
};
}  // namespace frontier_exploration
#endif
