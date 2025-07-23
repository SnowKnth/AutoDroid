// 让Bootstrap模态框可拖动（方法1：jQuery UI）
$(document).ready(function () {
  $('#chatModal').on('shown.bs.modal', function () {
    $(this).find('.modal-dialog').draggable({
      handle: ".modal-header",
      cursor: 'move'
    });
  });
});
async function showFinalSubtasks() {
  // 获取utg_details元素
  const utg_details = document.getElementById('utg_details');
  // 设置加载提示，提升用户体验
  utg_details.innerHTML = '<h2>Updated test subtasks</h2><p>Loading...</p>';

  const dirPath = '../captured_data/updated_instruction/';

  try {
    // 1. 异步获取目录列表
    const response = await fetch(dirPath);
    if (!response.ok) {
      throw new Error(`Failed to fetch directory list: ${response.statusText}`);
    }
    const directoryHtml = await response.text();

    // 2. 解析目录内容，找到所有.instruction文件
    const matches = directoryHtml.match(/(\d+)\.instruction/g);
    if (!matches || matches.length === 0) {
      utg_details.innerHTML = '<h2>Updated test subtasks</h2><p>[No instruction file found]</p>';
      return;
    }

    const fileNumbers = matches.map(f => parseInt(f, 10));

    // 3. 找到数字最大的文件名
    const maxK = Math.max(...fileNumbers);
    const fileName = `${maxK}.instruction`;
    const filePath = dirPath + fileName;

    // 4. 异步读取最新的文件内容
    const fileResponse = await fetch(filePath);
    if (!fileResponse.ok) {
      throw new Error(`Failed to fetch instruction file: ${fileResponse.statusText}`);
    }
    const content = await fileResponse.text();

    // 5. 显示内容，并对HTML特殊字符进行转义以防止XSS
    const sanitizedContent = content.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    utg_details.innerHTML = `<h2>Updated test subtasks</h2><p style="white-space:pre-wrap;">${sanitizedContent}</p>`;
  } catch (error) {
    console.error('Error in showFinalSubtasks:', error);
    utg_details.innerHTML = '<h2>Updated test subtasks</h2><p>[Error loading instruction data]</p>';
  }
}
var network = null;

function draw() {
  var utg_div = document.getElementById('utg_div');
  var utg_details = document.getElementById('utg_details');

  showOverall();

  var options = {
    autoResize: true,
    height: '100%',
    width: '100%',
    locale: 'en',

    nodes: {
      shapeProperties: {
        useBorderWithImage: true
      },

      borderWidth: 0,
      borderWidthSelected: 5,

      color: {
        border: '#FFFFFF',
        background: '#FFFFFF',

        highlight: {
          border: '#0000FF',
          background: '#0000FF',
        }
      },

      font: {
        size: 12,
        color: '#000'
      }
    },
    edges: {
      color: 'black',
      arrows: {
        to: {
          enabled: true,
          scaleFactor: 0.5
        }
      },
      font: {
        size: 12,
        color: '#000'
      }
    }
  };

  network = new vis.Network(utg_div, utg, options);

  network.on("click", function (params) {
    if (params.nodes.length > 0) {
      node = params.nodes[0];
      if (network.isCluster(node)) {
        utg_details.innerHTML = getClusterDetails(node);
      }
      else {
        utg_details.innerHTML = getNodeDetails(node);
      }
    }
    else if (params.edges.length > 0) {
      edge = params.edges[0];
      baseEdge = network.clustering.getBaseEdge(edge)
      if (baseEdge == null || baseEdge == edge) {
        utg_details.innerHTML = getEdgeDetails(edge);
      } else {
        utg_details.innerHTML = getEdgeDetails(baseEdge);
      }
    }
  });
}

function showOverall() {
  var utg_details = document.getElementById('utg_details');
  utg_details.innerHTML = getOverallResult();
}

function getOverallResult() {
  var overallInfo = "<hr />";
  overallInfo += "<table class=\"table\">\n"

  overallInfo += "<tr class=\"active\"><th colspan=\"2\"><h4>App information</h4></th></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\">Package</th><td class=\"col-md-4\">" + utg.app_package + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\">SHA-256</th><td class=\"col-md-4\">" + utg.app_sha256 + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\">Main activity</th><td class=\"col-md-4\">" + utg.app_main_activity + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\"># activities</th><td class=\"col-md-4\">" + utg.app_num_total_activities + "</td></tr>\n";

  overallInfo += "<tr class=\"active\"><th colspan=\"2\"><h4>Device information</h4></th></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\">Device serial</th><td class=\"col-md-4\">" + utg.device_serial + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\">Model number</th><td class=\"col-md-4\">" + utg.device_model_number + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\">SDK version</th><td class=\"col-md-4\">" + utg.device_sdk_version + "</td></tr>\n";

  overallInfo += "<tr class=\"active\"><th colspan=\"2\"><h4>Statistics</h4></th></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\">Test date</th><td class=\"col-md-4\">" + utg.test_date + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\">Time spent (s)</th><td class=\"col-md-4\">" + utg.time_spent + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\"># input events</th><td class=\"col-md-4\">" + utg.num_input_events + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\"># UTG states</th><td class=\"col-md-4\">" + utg.num_nodes + "</td></tr>\n";
  overallInfo += "<tr><th class=\"col-md-1\"># UTG edges</th><td class=\"col-md-4\">" + utg.num_edges + "</td></tr>\n";
  // activity_coverage = 100 * utg.num_reached_activities / utg.app_num_total_activities;
  // overallInfo += "<tr><th class=\"col-md-1\">Activity_coverage</th><td class=\"col-md-4 progress\"><div class=\"progress-bar\" role=\"progressbar\" aria-valuenow=\"" + utg.num_reached_activities + "\" aria-valuemin=\"0\" aria-valuemax=\"" + utg.app_num_total_activities + "\" style=\"width: " + activity_coverage + "%;\">" + utg.num_reached_activities + "/" + utg.app_num_total_activities + "</div></td></tr>\n";

  overallInfo += "</table>";
  return overallInfo;
}

function getEdgeDetails(edgeId) {
  var selectedEdge = getEdge(edgeId);
  edgeInfo = "<h2>Transition Details</h2><hr/>\n";
  fromState = getNode(selectedEdge.from);
  toState = getNode(selectedEdge.to);
  edgeInfo += "<img class=\"col-md-5\" src=\"" + fromState.image + "\">\n"
  edgeInfo += "<div class=\"col-md-2 text-center\">TO</div>\n"
  edgeInfo += "<img class=\"col-md-5\" src=\"" + toState.image + "\">\n"
  edgeInfo += "<table class=\"table table-striped\">\n"
  edgeInfo += "<tr class=\"active\"><th colspan=\"4\"><h4>Events</h4></th></tr>\n";

  var i;
  edgeInfo += "<tr><th style=\"width: 50%;\">id (click to see chat)</th><th>type</th><th>view</th><th>event_str</th></tr>\n"
  for (i = 0; i < selectedEdge.events.length; i++) {
    event = selectedEdge.events[i];
    // 对 event.event_str 进行 HTML 转义
    eventStr = event.event_str.replace(/</g, "&lt;").replace(/>/g, "&gt;");
    var viewImg = "";
    if (event.view_images != null) {
      var j;
      for (j = 0; j < event.view_images.length; j++) {
        viewImg += "<img class=\"viewImg\" src=\"" + event.view_images[j] + "\">\n"
      }
    }
    edgeInfo += "<tr><td><a href=\"#\" onclick=\"showChatInModal(" + event.event_id + "); return false;\">" + event.event_id + "</a></td><td>" + event.event_type + "</td><td>" + viewImg + "</td><td>" + eventStr + "</td></tr>"
  }
  edgeInfo += "</table>\n"
  return edgeInfo;
}

async function showChatInModal(eventId) {
  const chatId = eventId - 1;
  const chatFilePath = `../captured_data/chat/${chatId}.chat`;

  // Since bootstrap.min.js and jquery.min.js are included, we can use jQuery for modals.
  const modal = $('#chatModal');
  const modalTitle = $('#chatModalLabel');
  const modalBody = $('#chatModalBody');

  // 1. Set title and loading state
  modalTitle.text(`Observe-Think-Act Process for Event ${eventId}`);
  modalBody.html(`<p>Loading Chat Log (File: ${chatId}.chat)...</p>`);

  // 2. Show the modal
  modal.modal('show');

  try {
    // 3. Asynchronously fetch the content
    const response = await fetch(chatFilePath);
    if (!response.ok) {
      throw new Error(`File not found or server error: ${response.statusText}`);
    }
    const content = await response.text();
    const sanitizedContent = content.replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // 4. Update modal body with the fetched content
    modalBody.html(`<pre style="white-space: pre-wrap; word-wrap: break-word;">${sanitizedContent}</pre>`);
  } catch (error) {
    console.error(`Error loading chat file for event ${eventId}:`, error);
    modalBody.html(`<p style="color: red;"><b>Error:</b> Could not load chat content. ${error.message}</p>`);
  }
}

function getNodeDetails(nodeId) {
  var selectedNode = getNode(nodeId);
  stateInfo = "<h2>State Details</h2><hr/>\n";
  stateInfo += "<img class=\"col-md-5\" src=\"" + selectedNode.image + "\">"
  stateInfo += "<div class=\"col-md-7\">" + selectedNode.title + "</div>";
  return stateInfo;
}

function getClusterDetails(clusterId) {
  clusterInfo = "<h2>Cluster Details</h2><hr/>\n";
  var nodeIds = network.getNodesInCluster(clusterId);
  for (var i = 0; i < nodeIds.length; i++) {
    var selectedNode = getNode(nodeIds[i]);
    clusterInfo += "<div class=\"row\">\n"
    clusterInfo += "<img class=\"col-md-5\" src=\"" + selectedNode.image + "\">"
    clusterInfo += "<div class=\"col-md-7\">" + selectedNode.title + "</div>";
    clusterInfo += "</div><br />"
  }
  return clusterInfo;
}

function getEdge(edgeId) {
  var i, numEdges;
  numEdges = utg.edges.length;
  for (i = 0; i < numEdges; i++) {
    if (utg.edges[i].id == edgeId) {
      return utg.edges[i];
    }
  }
  console.log("cannot find edge: " + edgeId);
}

function getNode(nodeId) {
  var i, numNodes;
  numNodes = utg.nodes.length;
  for (i = 0; i < numNodes; i++) {
    if (utg.nodes[i].id == nodeId) {
      return utg.nodes[i];
    }
  }
  console.log("cannot find node: " + nodeId);
}

function showAbout() {
  var utg_details = document.getElementById('utg_details');
  utg_details.innerHTML = getAboutInfo();
}

function getAboutInfo() {
  var aboutInfo = "<hr />";
  aboutInfo += "<h2>About</h2>\n"
  aboutInfo += "<p>This report is generated using updated report generator for subtask-driven GUI test case generation based on  <a href=\"https://github.com/honeynet/droidbot\">DroidBot</a>.</p>\n";
  aboutInfo += "<p>Please find copyright information in the project page.</p>";
  return aboutInfo;
}

function searchUTG() {
  var searchKeyword = document.getElementById("utgSearchBar").value.toUpperCase();
  if (searchKeyword == null || searchKeyword == "") {
    network.unselectAll()
  } else {
    var i, numNodes;
    nodes = utg.nodes;
    numNodes = nodes.length;
    selectedNodes = []
    for (i = 0; i < numNodes; i++) {
      if (nodes[i].content.toUpperCase().indexOf(searchKeyword) > -1) {
        selectedNodes.push(nodes[i].id)
      }
    }
    network.unselectAll()
    // console.log("Selecting: " + selectedNodes)
    network.selectNodes(selectedNodes, false)
  }
}

function clusterStructures() {
  network.setData(utg)
  var structures = [];

  for (var i = 0; i < utg.nodes.length; i++) {
    node = utg.nodes[i]
    if (structures.indexOf(node.structure_str) < 0) {
      structures.push(node.structure_str)
    }
  }

  var clusterOptionsByData;
  for (var i = 0; i < structures.length; i++) {
    var structure = structures[i];
    clusterOptionsByData = {
      joinCondition: function (childOptions) {
        return childOptions.structure_str == structure;
      },
      processProperties: function (clusterOptions, childNodes, childEdges) {
        clusterOptions.title = childNodes[0].title;
        clusterOptions.state_str = childNodes[0].state_str;
        clusterOptions.label = childNodes[0].label;
        clusterOptions.image = childNodes[0].image;
        return clusterOptions;
      },
      clusterNodeProperties: { id: 'structure:' + structure, shape: 'image' }
    };
    network.cluster(clusterOptionsByData);
  }
}

function clusterActivities() {
  network.setData(utg)
  var activities = [];

  for (var i = 0; i < utg.nodes.length; i++) {
    node = utg.nodes[i]
    if (activities.indexOf(node.activity) < 0) {
      activities.push(node.activity)
    }
  }

  var clusterOptionsByData;
  for (var i = 0; i < activities.length; i++) {
    var activity = activities[i];
    clusterOptionsByData = {
      joinCondition: function (childOptions) {
        return childOptions.activity == activity;
      },
      processProperties: function (clusterOptions, childNodes, childEdges) {
        clusterOptions.title = childNodes[0].title;
        clusterOptions.state_str = childNodes[0].state_str;
        clusterOptions.label = childNodes[0].label;
        clusterOptions.image = childNodes[0].image;
        return clusterOptions;
      },
      clusterNodeProperties: { id: 'activity:' + activity, shape: 'image' }
    };
    network.cluster(clusterOptionsByData);
  }
}

function showOriginalUTG() {
  network.setData(utg)
  network.redraw()
}
