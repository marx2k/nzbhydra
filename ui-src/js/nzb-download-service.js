angular
    .module('nzbhydraApp')
    .factory('NzbDownloadService', NzbDownloadService);

function NzbDownloadService($http, ConfigService, CategoriesService) {
    
    var service = {
        download: download 
    };
    
    return service;
    


    function sendNzbAddCommand(guids, category) {
        console.log("Now add nzb with category " + category);        
        return $http.put("internalapi/addnzbs", {guids: angular.toJson(guids), category: category});
    }

    function download (guids) {
        return ConfigService.getSafe().then(function (settings) {

            var category;
            if (settings.downloader.downloader == "nzbget") {
                category = settings.downloader.nzbget.defaultCategory
            } else {
                category = settings.downloader.sabnzbd.defaultCategory
            }

            if (_.isUndefined(category) || category == "" || category == null) {
                return CategoriesService.openCategorySelection().then(function (category) {
                    return sendNzbAddCommand(guids, category)
                }, function(error) {
                    throw error;
                });
            } else {
                return sendNzbAddCommand(guids, category)
            }

        });


    }

    
}

